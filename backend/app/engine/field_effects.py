"""Field effects: smoke fog, and support-drone transport."""

from __future__ import annotations

from uuid import uuid4

from ..content.loader import ContentCatalog
from ..domain.enums import ActionType, Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance, hex_key, hexes_in_radius
from .pathfinding import find_path
from .state import (
    BattleState,
    FieldEffect,
    UnitState,
    evaluate_terminal,
    in_signal,
    signal_radius,
)


def resolve_drop_smoke(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
) -> list[DomainEvent]:
    ability = catalog.abilities.get("drop_smoke")
    if not ability:
        raise ValueError("Smoke ability missing from catalog")
    events: list[DomainEvent] = []
    if battle.activation and battle.activation.actor_id == unit.unit_instance_id:
        used = battle.activation.actions.spend(ActionType.MINOR)
        events.append(
            DomainEvent(
                type="action_spent",
                actor_id=unit.unit_instance_id,
                payload={"action": used.value, "for": "drop_smoke"},
            )
        )
    radius = int(getattr(ability, "area", 2) or 2)
    duration = 2
    center = unit.position
    battle.field_effects.append(
        FieldEffect(
            effect_id=f"smoke-{uuid4().hex[:8]}",
            effect_type="smoke",
            center=Hex(center.q, center.r),
            radius=radius,
            rounds_remaining=duration,
            side=unit.side,
            source_unit_id=unit.unit_instance_id,
        )
    )
    affected = [h.to_dict() for h in hexes_in_radius(center, radius, battle.width, battle.height)]
    events.append(
        DomainEvent(
            type="field_effect_placed",
            actor_id=unit.unit_instance_id,
            payload={"effect_type": "smoke", "center": center.to_dict(), "radius": radius, "affected_hexes": affected, "rounds": duration},
        )
    )
    return events


def find_support_drone(battle: BattleState, side: Side = Side.FRIENDLY) -> UnitState | None:
    if battle.support_drone_unit_id and battle.support_drone_unit_id in battle.units:
        drone = battle.units[battle.support_drone_unit_id]
        if drone.alive and drone.side == side:
            return drone
    for u in battle.living_units(side):
        if u.definition_id == "friendly_commander_support_drone" and side == Side.FRIENDLY:
            return u
        if u.definition_id == "opposition_tank" and side == Side.OPPOSITION:
            return u
    return None


def commander_embarked(battle: BattleState) -> bool:
    cmd = battle.commander()
    return bool(cmd and cmd.alive and cmd.embarked_in)


def embark_commander(catalog: ContentCatalog, battle: BattleState, drone: UnitState, commander: UnitState) -> list[DomainEvent]:
    if commander.embarked_in:
        raise ValueError("Commander already embarked")
    if drone.embarked_commander_id:
        raise ValueError("Support drone already occupied")
    if axial_distance(commander.position, drone.position) > 1:
        raise ValueError("Commander must be adjacent to embark")
    commander.embarked_in = drone.unit_instance_id
    drone.embarked_commander_id = commander.unit_instance_id
    commander.position = Hex(drone.position.q, drone.position.r)
    commander.signal_range = (commander.signal_range or signal_radius(commander)) + 4
    commander.ram_capacity = (commander.ram_capacity or 6) + 2
    commander.ram_current = min((commander.ram_current or 0) + 2, commander.ram_capacity)
    for m in commander.models:
        if m.alive and m.position:
            m.position = Hex(drone.position.q, drone.position.r)
    return [
        DomainEvent(
            type="commander_embarked",
            payload={"commander_id": commander.unit_instance_id, "drone_id": drone.unit_instance_id, "position": drone.position.to_dict()},
        )
    ]


def disembark_hex(drone: UnitState, battle: BattleState) -> Hex:
    """Exit one hex 'below' the drone toward the friendly deploy edge (+r)."""
    # Prefer south / SE / SW neighbors on the odd-r brick map
    preferred = [
        Hex(drone.position.q, drone.position.r + 1),
        Hex(drone.position.q + 1, drone.position.r + 1),
        Hex(drone.position.q - 1, drone.position.r + 1),
        Hex(drone.position.q + 1, drone.position.r),
        Hex(drone.position.q - 1, drone.position.r),
    ]
    neighbor_set = {(h.q, h.r) for h in drone.position.neighbors()}
    for h in preferred:
        if (h.q, h.r) in neighbor_set and 0 <= h.q < battle.width and 0 <= h.r < battle.height:
            return h
    for h in drone.position.neighbors():
        if 0 <= h.q < battle.width and 0 <= h.r < battle.height:
            return h
    return Hex(drone.position.q, min(battle.height - 1, drone.position.r + 1))


def disembark_commander(battle: BattleState, commander: UnitState) -> list[DomainEvent]:
    if not commander.embarked_in:
        raise ValueError("Commander is not embarked")
    drone = battle.units.get(commander.embarked_in)
    if not drone or not drone.alive:
        raise ValueError("Support drone unavailable")
    dest = disembark_hex(drone, battle)
    drone.embarked_commander_id = None
    commander.embarked_in = None
    commander.signal_range = max(12, (commander.signal_range or 16) - 4)
    commander.ram_capacity = max(6, (commander.ram_capacity or 8) - 2)
    commander.ram_current = min(commander.ram_current or 0, commander.ram_capacity)
    commander.position = dest
    for m in commander.models:
        if m.alive:
            m.position = dest
    return [
        DomainEvent(
            type="commander_disembarked",
            payload={"commander_id": commander.unit_instance_id, "drone_id": drone.unit_instance_id, "position": dest.to_dict()},
        )
    ]


def resolve_call_support_drone(catalog: ContentCatalog, battle: BattleState, commander: UnitState) -> list[DomainEvent]:
    drone = find_support_drone(battle, Side.FRIENDLY)
    if not drone or not drone.alive:
        raise ValueError("No support drone in battle")
    if commander.embarked_in:
        raise ValueError("Already aboard support drone")
    if "summoned_load" not in drone.statuses:
        drone.statuses.append("summoned_load")
    return [
        DomainEvent(
            type="support_drone_summoned",
            actor_id=commander.unit_instance_id,
            payload={"drone_id": drone.unit_instance_id},
        )
    ]


def resolve_leave_support_drone(battle: BattleState, commander: UnitState) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    if battle.activation and battle.activation.actor_id == commander.unit_instance_id:
        used = battle.activation.actions.spend(ActionType.MINOR)
        events.append(
            DomainEvent(
                type="action_spent",
                actor_id=commander.unit_instance_id,
                payload={"action": used.value, "for": "leave_support_drone"},
            )
        )
    events.extend(disembark_commander(battle, commander))
    return events


def try_support_drone_auto_load(catalog: ContentCatalog, battle: BattleState, drone: UnitState) -> list[DomainEvent]:
    """On support drone activation: move toward commander up to 20 hex, then load if adjacent."""
    if drone.embarked_commander_id or "summoned_load" not in drone.statuses:
        return []
    cmd = battle.commander()
    if not cmd or not cmd.alive or cmd.embarked_in:
        drone.statuses = [s for s in drone.statuses if s != "summoned_load"]
        return []
    events: list[DomainEvent] = []
    dist = axial_distance(drone.position, cmd.position)
    if dist <= 1:
        drone.statuses = [s for s in drone.statuses if s != "summoned_load"]
        events.extend(embark_commander(catalog, battle, drone, cmd))
        return events
    path = find_path(catalog, battle, drone, cmd.position, max_cost=20)
    if path and len(path) >= 2:
        move_hexes = min(20, len(path) - 1)
        dest = path[move_hexes]
        drone.position = dest
        for m in drone.models:
            if m.alive:
                m.position = dest
        events.append(
            DomainEvent(
                type="unit_moved",
                actor_id=drone.unit_instance_id,
                payload={"path": [p.to_dict() for p in path[: move_hexes + 1]], "to": dest.to_dict(), "reason": "support_drone_summoned"},
            )
        )
        if axial_distance(dest, cmd.position) <= 1:
            drone.statuses = [s for s in drone.statuses if s != "summoned_load"]
            events.extend(embark_commander(catalog, battle, drone, cmd))
    return events


def apply_embarked_commander_bonuses(commander: UnitState, drone: UnitState) -> None:
    pass  # bonuses applied inline in embark_commander / disembark_commander


def resolve_embarked_drone_destroyed(catalog: ContentCatalog, battle: BattleState, drone: UnitState) -> list[DomainEvent]:
    if not drone.embarked_commander_id:
        return []
    cmd = battle.units.get(drone.embarked_commander_id)
    if not cmd or not cmd.alive:
        return []
    from .combat import _resolve_aoe

    cmd.embarked_in = None
    drone.embarked_commander_id = None
    rng = battle.rng()
    events = _resolve_aoe(catalog, battle, drone, "support_drone_collapse", 10, 1, drone.position, rng)
    battle.commit_rng(rng)
    terminal = evaluate_terminal(battle)
    if terminal:
        battle.status = terminal
        battle.result = terminal.value
        events.append(DomainEvent(type="battle_completed", payload={"status": terminal.value}))
    return events
