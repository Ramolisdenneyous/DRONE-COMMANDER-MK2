"""Anti-personnel mines: deploy, detect, trigger."""

from __future__ import annotations

from uuid import uuid4

from ..content.loader import ContentCatalog
from ..domain.enums import ActionType, BattleStatus, Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance, hex_key, in_bounds
from .state import BattleState, MineState, UnitState, evaluate_terminal

DETECT_MINE_RANGE = 5
MINE_DAMAGE = 10
MINE_AREA = 1


def _ability_detect_range(catalog: ContentCatalog) -> int:
    ability = catalog.abilities.get("detect_mine")
    if ability and ability.range is not None:
        return int(ability.range)
    return DETECT_MINE_RANGE


def _ability_mine_stats(catalog: ContentCatalog) -> tuple[int, int]:
    ability = catalog.abilities.get("deploy_mine")
    damage = int(ability.damage) if ability and ability.damage is not None else MINE_DAMAGE
    area = int(ability.area) if ability and ability.area is not None else MINE_AREA
    return damage, area


def mine_at(battle: BattleState, hex_: Hex) -> MineState | None:
    key = hex_key(hex_)
    for mine in battle.mines:
        if mine.armed and hex_key(mine.position) == key:
            return mine
    return None


def unit_occupies_hex(unit: UnitState, hex_: Hex) -> bool:
    key = hex_key(hex_)
    if hex_key(unit.position) == key:
        return True
    for m in unit.living_models:
        pos = unit.model_position(m)
        if hex_key(pos) == key:
            return True
    return False


def adjacent_deploy_hexes(battle: BattleState, unit: UnitState) -> list[Hex]:
    """Any in-bounds neighbor. May be empty or enemy-occupied; not friendly-occupied."""
    occ = battle.occupancy()
    out: list[Hex] = []
    seen: set[str] = set()
    anchors = [unit.model_position(m) for m in unit.living_models] or [unit.position]
    for anchor in anchors:
        for h in anchor.neighbors():
            key = hex_key(h)
            if key in seen:
                continue
            seen.add(key)
            if not in_bounds(h, battle.width, battle.height):
                continue
            if mine_at(battle, h):
                continue
            occupant_id = occ.get(key)
            if occupant_id:
                other = battle.units.get(occupant_id)
                if other and other.alive and other.side == unit.side and other.category != "decoy":
                    continue
            out.append(h)
    return out


def refresh_detect_mines(catalog: ContentCatalog, battle: BattleState) -> list[DomainEvent]:
    """Passive Detect Mine: engineers reveal hostile mines within range."""
    detect_range = _ability_detect_range(catalog)
    events: list[DomainEvent] = []
    engineers = [
        u
        for u in battle.units.values()
        if u.alive and "detect_mine" in u.abilities and u.category != "decoy"
    ]
    for eng in engineers:
        for mine in battle.mines:
            if not mine.armed or mine.revealed or mine.side == eng.side:
                continue
            nearest = min(
                (axial_distance(eng.model_position(m), mine.position) for m in eng.living_models),
                default=axial_distance(eng.position, mine.position),
            )
            if nearest <= detect_range:
                mine.revealed = True
                events.append(
                    DomainEvent(
                        type="mine_revealed",
                        actor_id=eng.unit_instance_id,
                        payload={
                            "mine_id": mine.mine_id,
                            "position": mine.position.to_dict(),
                            "side": mine.side.value,
                            "reason": "detect_mine",
                            "detector_id": eng.unit_instance_id,
                        },
                    )
                )
    return events


def resolve_deploy_mine(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    target: Hex,
) -> list[DomainEvent]:
    if "deploy_mine" not in unit.abilities:
        raise ValueError("Unit cannot deploy mines")
    if not battle.activation or battle.activation.actor_id != unit.unit_instance_id:
        raise ValueError("Deploy Mine requires active activation")
    if not battle.activation.actions.can_spend(ActionType.STANDARD):
        raise ValueError("Deploy Mine requires a Standard action (replaces Attack)")
    legal = {hex_key(h) for h in adjacent_deploy_hexes(battle, unit)}
    if hex_key(target) not in legal:
        raise ValueError("Mine must be placed on an adjacent legal hex")
    if mine_at(battle, target):
        raise ValueError("Hex already mined")

    damage, area = _ability_mine_stats(catalog)
    used = battle.activation.actions.spend(ActionType.STANDARD)
    mine = MineState(
        mine_id=f"mine-{uuid4().hex[:8]}",
        position=Hex(target.q, target.r),
        side=unit.side,
        damage=damage,
        area=area,
        revealed=False,
        armed=True,
        source_unit_id=unit.unit_instance_id,
    )
    battle.mines.append(mine)
    events: list[DomainEvent] = [
        DomainEvent(
            type="action_spent",
            actor_id=unit.unit_instance_id,
            payload={"action": used.value, "for": "deploy_mine"},
        ),
        DomainEvent(
            type="mine_deployed",
            actor_id=unit.unit_instance_id,
            payload={
                "mine_id": mine.mine_id,
                "position": mine.position.to_dict(),
                "side": mine.side.value,
                "damage": mine.damage,
                "area": mine.area,
                "animation": {
                    "type": "deploy_mine",
                    "unit_id": unit.unit_instance_id,
                    "to": mine.position.to_dict(),
                },
            },
        ),
    ]
    events.extend(refresh_detect_mines(catalog, battle))
    # Planted under an enemy: detonate now (planter's turn — they cannot walk off mid-plant).
    # Activation-start / enter-hex still covers mines stepped on later.
    for other in list(battle.living_units()):
        if other.side == unit.side or other.category == "decoy":
            continue
        if unit_occupies_hex(other, mine.position):
            events.extend(check_unit_triggers_mines(catalog, battle, other, reason="planted_under"))
            break
    return events


def trigger_mine(
    catalog: ContentCatalog,
    battle: BattleState,
    mine: MineState,
    trigger_unit: UnitState,
    reason: str,
) -> list[DomainEvent]:
    if not mine.armed:
        return []
    from .combat import _resolve_aoe

    mine.armed = False
    mine.revealed = True
    owner = battle.units.get(mine.source_unit_id)
    # AOE needs an attacker UnitState; prefer living owner, else the victim as proxy actor id.
    attacker = owner if owner else trigger_unit
    rng = battle.rng()
    events: list[DomainEvent] = [
        DomainEvent(
            type="mine_triggered",
            actor_id=trigger_unit.unit_instance_id,
            payload={
                "mine_id": mine.mine_id,
                "position": mine.position.to_dict(),
                "side": mine.side.value,
                "reason": reason,
                "source_unit_id": mine.source_unit_id,
                "damage": mine.damage,
                "area": mine.area,
                "animation": {
                    "type": "mine_explosion",
                    "at": mine.position.to_dict(),
                    "area": mine.area,
                },
            },
        )
    ]
    events.extend(
        _resolve_aoe(
            catalog,
            battle,
            attacker,
            "anti_personnel_mine",
            mine.damage,
            mine.area,
            mine.position,
            rng,
        )
    )
    battle.commit_rng(rng)
    # Drop spent mine from board
    battle.mines = [m for m in battle.mines if m.mine_id != mine.mine_id]
    events.append(
        DomainEvent(
            type="mine_cleared",
            payload={"mine_id": mine.mine_id, "reason": "triggered"},
        )
    )
    terminal = evaluate_terminal(battle)
    if terminal:
        battle.status = terminal
        battle.result = terminal.value
        events.append(DomainEvent(type="battle_completed", payload={"status": terminal.value}))
    return events


def check_unit_triggers_mines(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    reason: str,
) -> list[DomainEvent]:
    """Enemy mines under this unit's models explode (friendly mines ignored)."""
    if not unit.alive or unit.category == "decoy":
        return []
    events: list[DomainEvent] = []
    # Snapshot list — triggering mutates battle.mines
    for mine in list(battle.mines):
        if not mine.armed or mine.side == unit.side:
            continue
        if unit_occupies_hex(unit, mine.position):
            events.extend(trigger_mine(catalog, battle, mine, unit, reason))
            if not unit.alive or battle.status != BattleStatus.ACTIVE:
                break
    return events


def reveal_enemy_mines_satellite(battle: BattleState, viewer_side: Side) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    for mine in battle.mines:
        if not mine.armed or mine.side == viewer_side:
            continue
        if mine.revealed:
            continue
        mine.revealed = True
        events.append(
            DomainEvent(
                type="mine_revealed",
                payload={
                    "mine_id": mine.mine_id,
                    "position": mine.position.to_dict(),
                    "side": mine.side.value,
                    "reason": "satellite_sweep",
                },
            )
        )
    return events


def mines_for_snapshot(battle: BattleState, viewer_side: Side = Side.FRIENDLY) -> list[dict]:
    """Owner always sees own mines; foes only see revealed ones."""
    out: list[dict] = []
    for mine in battle.mines:
        if not mine.armed:
            continue
        if mine.side != viewer_side and not mine.revealed:
            continue
        out.append(
            {
                "mine_id": mine.mine_id,
                "position": mine.position.to_dict(),
                "side": mine.side.value,
                "damage": mine.damage,
                "area": mine.area,
                "revealed": mine.revealed or mine.side == viewer_side,
                "source_unit_id": mine.source_unit_id,
                "hidden_from_enemy": mine.side == viewer_side and not mine.revealed,
            }
        )
    return out
