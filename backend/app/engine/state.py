"""In-memory authoritative battle state and resolution helpers."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from ..content.loader import ContentCatalog, get_catalog
from ..domain.enums import ActionType, BattleStatus, Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance, cube_line, hex_key, hexes_in_radius, in_bounds, parse_hex
from ..domain.rng import SeededRNG


COVER_DEFENSE = {"none": 0, "light": 2, "heavy": 4}


@dataclass
class ModelState:
    model_id: str
    hp: int
    max_hp: int
    alive: bool = True
    position: Hex | None = None  # None when destroyed / not placed


def _model_sort_key(model_id: str) -> int:
    try:
        return int(str(model_id).lstrip("mM"))
    except ValueError:
        return 0


@dataclass
class UnitState:
    unit_instance_id: str
    definition_id: str
    display_name: str
    side: Side
    category: str
    roles: list[str]
    asset_set_id: str
    position: Hex
    speed: int
    attack: int
    defense: int
    armor: int
    models: list[ModelState]
    weapons: list[str]
    abilities: list[str]
    movement_traits: list[str]
    size_class: str = "medium"
    statuses: list[str] = field(default_factory=list)
    ammo: dict[str, int] = field(default_factory=dict)
    alive: bool = True
    activated_this_round: bool = False
    # Commander-only
    ram_current: int | None = None
    ram_capacity: int | None = None
    signal_range: int | None = None
    used_once_abilities: list[str] = field(default_factory=list)
    embarked_in: str | None = None  # commander → support drone unit id while aboard
    embarked_commander_id: str | None = None  # support drone → commander id
    # Control Phase: RAM allocated to this unit (drones); spent into ActionPool on next activation
    allocated_ram: int = 0

    @property
    def living_models(self) -> list[ModelState]:
        return [m for m in self.models if m.alive]

    @property
    def total_hp(self) -> int:
        return sum(m.hp for m in self.living_models)

    @property
    def is_flying(self) -> bool:
        return "flying" in self.movement_traits

    @property
    def is_multi_model(self) -> bool:
        return self.category == "soldier_squad" or len(self.models) > 1

    def leader_model(self) -> ModelState | None:
        living = self.living_models
        if not living:
            return None
        return max(living, key=lambda m: _model_sort_key(m.model_id))

    def model_position(self, model: ModelState | None = None) -> Hex:
        """Map hex for a model, falling back to unit.position."""
        if model is not None and model.position is not None:
            return model.position
        lead = self.leader_model()
        if lead and lead.position is not None:
            return lead.position
        return self.position

    def sync_position_from_leader(self) -> None:
        lead = self.leader_model()
        if lead and lead.position is not None:
            self.position = lead.position

    def place_models_at(self, positions: dict[str, Hex]) -> None:
        for m in self.models:
            if not m.alive:
                m.position = None
                continue
            if m.model_id in positions:
                m.position = positions[m.model_id]
        self.sync_position_from_leader()


@dataclass
class FieldEffect:
    effect_id: str
    effect_type: str  # smoke
    center: Hex
    radius: int
    rounds_remaining: int
    side: Side
    source_unit_id: str = ""


@dataclass
class MineState:
    mine_id: str
    position: Hex
    side: Side
    damage: int = 10
    area: int = 1
    revealed: bool = False
    armed: bool = True
    source_unit_id: str = ""


@dataclass
class ControlPhaseState:
    """Warmachine-style Control Phase — allocate RAM before the commander acts."""

    active: bool = True
    side: Side = Side.FRIENDLY
    commander_id: str = ""


@dataclass
class ActionPool:
    standard: int = 1
    move: int = 1
    minor: int = 1
    # How many Move spends this activation (Move pool or Standard-as-move).
    # After 2, Attack is illegal even if Standard somehow remains.
    moves_spent: int = 0

    def can_spend(self, kind: ActionType) -> bool:
        if kind == ActionType.STANDARD:
            return self.can_attack()
        if kind == ActionType.MOVE:
            return self.move >= 1 or self.standard >= 1
        if kind == ActionType.MINOR:
            return self.minor >= 1 or self.move >= 1 or self.standard >= 1
        return False

    def can_attack(self) -> bool:
        """Attack needs Standard, and you cannot attack after a double-move."""
        return self.standard >= 1 and self.moves_spent < 2

    def spend(self, kind: ActionType) -> ActionType:
        """Spend with downgrades; returns actual pool bucket consumed."""
        if kind == ActionType.STANDARD:
            if not self.can_attack():
                raise ValueError("No Standard action remaining")
            self.standard -= 1
            return ActionType.STANDARD
        if kind == ActionType.MOVE:
            if self.move >= 1:
                self.move -= 1
                self.moves_spent += 1
                return ActionType.MOVE
            if self.standard >= 1:
                self.standard -= 1
                self.moves_spent += 1
                return ActionType.STANDARD
            raise ValueError("No Move action remaining")
        if kind == ActionType.MINOR:
            if self.minor >= 1:
                self.minor -= 1
                return ActionType.MINOR
            if self.move >= 1:
                self.move -= 1
                self.moves_spent += 1
                return ActionType.MOVE
            if self.standard >= 1:
                self.standard -= 1
                # Minor downgrade through Standard still burns the attack
                return ActionType.STANDARD
            raise ValueError("No Minor action remaining")
        raise ValueError(f"Unknown action {kind}")

    def to_dict(self) -> dict:
        return {
            "standard": self.standard,
            "move": self.move,
            "minor": self.minor,
            "moves_spent": self.moves_spent,
        }


@dataclass
class ActivationState:
    activation_id: str
    actor_id: str
    actions: ActionPool
    options: dict[str, dict] = field(default_factory=dict)


@dataclass
class BattleState:
    battle_id: str
    session_id: str
    seed: int
    content_version: str
    status: BattleStatus = BattleStatus.ACTIVE
    result: str | None = None
    mode: str = "freestyle_vs"
    mission_id: str = "freestyle_vs_15"
    point_cap: int = 15
    map_id: str = "vs_middle_east_50"
    width: int = 50
    height: int = 50
    round: int = 0
    state_version: int = 0
    event_sequence: int = 0
    terrain: dict[str, str] = field(default_factory=dict)  # "q,r" -> terrain_id
    units: dict[str, UnitState] = field(default_factory=dict)
    initiative: list[str] = field(default_factory=list)
    initiative_index: int = 0
    activation: ActivationState | None = None
    directives: list[dict] = field(default_factory=list)
    communications: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    pending_animation_batches: list[dict] = field(default_factory=list)
    rng_index: int = 0
    rng_state: Any | None = None
    commander_avatar: str = "male"
    loadout_id: str = "male"
    ram_abilities: list[str] = field(default_factory=list)
    opposition_ram_abilities: list[str] = field(default_factory=list)
    friendly_vp: int = 0
    opposition_vp: int = 0
    vp_to_win: int = 5
    objective_radius: int = 5
    scenario_id: str = "point_control"
    objective_type: str = "zone_control"
    objective_zones: list[dict] = field(default_factory=list)
    flags: list[dict] = field(default_factory=list)
    scenario_meta: dict = field(default_factory=dict)
    field_effects: list[FieldEffect] = field(default_factory=list)
    mines: list[MineState] = field(default_factory=list)
    support_drone_unit_id: str | None = None
    control_phase: ControlPhaseState | None = None

    def rng(self) -> SeededRNG:
        return SeededRNG(self.seed, state=self.rng_state, index=self.rng_index)

    def commit_rng(self, rng: SeededRNG) -> None:
        self.rng_index = rng.index
        self.rng_state = rng.snapshot_state()

    def append_events(self, domain_events: list[DomainEvent], batch_id: str | None = None) -> list[dict]:
        batch = batch_id or str(uuid4())
        self.state_version += 1
        envelopes: list[dict] = []
        for ev in domain_events:
            ev.batch_id = batch
            self.event_sequence += 1
            env = ev.to_envelope(
                session_id=self.session_id,
                battle_id=self.battle_id,
                sequence=self.event_sequence,
                state_version=self.state_version,
            )
            self.events.append(env)
            envelopes.append(env)
        return envelopes

    def append_standing_order_events(self, domain_events: list[DomainEvent], batch_id: str | None = None) -> list[dict]:
        """Log directive/comms updates without bumping state_version (safe during agent resolve)."""
        batch = batch_id or str(uuid4())
        envelopes: list[dict] = []
        for ev in domain_events:
            ev.batch_id = batch
            self.event_sequence += 1
            env = ev.to_envelope(
                session_id=self.session_id,
                battle_id=self.battle_id,
                sequence=self.event_sequence,
                state_version=self.state_version,
            )
            self.events.append(env)
            envelopes.append(env)
        return envelopes

    def living_units(self, side: Side | None = None) -> list[UnitState]:
        units = [u for u in self.units.values() if u.alive]
        if side is not None:
            units = [u for u in units if u.side == side]
        return units

    def commander(self) -> UnitState | None:
        return commander_for_side(self, Side.FRIENDLY)

    def occupancy(self) -> dict[str, str]:
        """Hex key -> unit_instance_id for every living model (or unit token)."""
        occ: dict[str, str] = {}
        for u in self.units.values():
            if not u.alive or u.category == "decoy":
                continue
            placed = False
            for m in u.living_models:
                if m.position is not None:
                    occ[hex_key(m.position)] = u.unit_instance_id
                    placed = True
            if not placed:
                occ[hex_key(u.position)] = u.unit_instance_id
        return occ

    def model_occupancy(self) -> dict[str, tuple[str, str]]:
        """Hex key -> (unit_instance_id, model_id)."""
        occ: dict[str, tuple[str, str]] = {}
        for u in self.units.values():
            if not u.alive or u.category == "decoy":
                continue
            for m in u.living_models:
                if m.position is not None:
                    occ[hex_key(m.position)] = (u.unit_instance_id, m.model_id)
                elif not u.is_multi_model:
                    occ[hex_key(u.position)] = (u.unit_instance_id, m.model_id)
        return occ

    def terrain_at(self, h: Hex) -> str:
        return self.terrain.get(hex_key(h), "clear")


def cover_bonus(catalog: ContentCatalog, battle: BattleState, hex_pos: Hex) -> int:
    bonus = 0
    if hex_in_smoke(battle, hex_pos):
        bonus = max(bonus, COVER_DEFENSE["light"])
    tid = battle.terrain_at(hex_pos)
    tdef = catalog.terrain.get(tid)
    if tdef:
        bonus = max(bonus, COVER_DEFENSE.get(tdef.cover, 0))
    return bonus


def move_cost(catalog: ContentCatalog, battle: BattleState, unit: UnitState, to_hex: Hex) -> int | None:
    tid = battle.terrain_at(to_hex)
    tdef = catalog.terrain.get(tid)
    if not tdef:
        return 1
    if unit.is_flying:
        return tdef.fly_move_cost
    return tdef.ground_move_cost


def smoke_hex_keys(battle: BattleState) -> set[str]:
    keys: set[str] = set()
    for fx in battle.field_effects:
        if fx.effect_type != "smoke" or fx.rounds_remaining <= 0:
            continue
        for h in hexes_in_radius(fx.center, fx.radius, battle.width, battle.height):
            keys.add(hex_key(h))
    return keys


def hex_in_smoke(battle: BattleState, h: Hex) -> bool:
    return hex_key(h) in smoke_hex_keys(battle)


def blocks_los(catalog: ContentCatalog, battle: BattleState, h: Hex) -> bool:
    if hex_in_smoke(battle, h):
        return True
    tid = battle.terrain_at(h)
    tdef = catalog.terrain.get(tid)
    return bool(tdef and tdef.blocks_los)


def has_line_of_sight(catalog: ContentCatalog, battle: BattleState, a: Hex, b: Hex) -> bool:
    line = cube_line(a, b)
    # Intermediate hexes only
    for h in line[1:-1]:
        if blocks_los(catalog, battle, h):
            return False
    return True


def effective_defense(
    catalog: ContentCatalog,
    battle: BattleState,
    target: UnitState,
    at_hex: Hex | None = None,
) -> int:
    hex_pos = at_hex if at_hex is not None else target.position
    bonus = cover_bonus(catalog, battle, hex_pos)
    if "defense_matrix" in target.statuses:
        bonus += 4
    return target.defense + bonus


def cohesion_ok(positions: list[Hex], max_dist: int) -> bool:
    """Every pair of living models must be within max_dist hexes."""
    for i, a in enumerate(positions):
        for b in positions[i + 1 :]:
            if axial_distance(a, b) > max_dist:
                return False
    return True


def commander_for_side(battle: BattleState, side: Side) -> UnitState | None:
    for u in battle.units.values():
        if u.category == "commander" and u.side == side and u.alive:
            return u
    return None


def commander_ram_abilities(battle: BattleState, commander: UnitState) -> list[str]:
    if commander.side == Side.FRIENDLY:
        return list(battle.ram_abilities or [])
    return list(getattr(battle, "opposition_ram_abilities", None) or [])


def within_commander_signal(battle: BattleState, position: Hex, *, side: Side | None = None) -> bool:
    target_side = side or Side.FRIENDLY
    cmd = commander_for_side(battle, target_side)
    if not cmd or not cmd.alive:
        return False
    return axial_distance(cmd.position, position) <= signal_radius(cmd)


def attack_modifier(battle: BattleState, attacker: UnitState, target: UnitState) -> int:
    """Situational attack bonuses/penalties beyond the unit's base Attack."""
    mod = 0
    if "jammed" in attacker.statuses:
        mod -= 2
    if "targeting_assisted" in attacker.statuses and attacker.category == "drone" and in_signal(battle, attacker):
        mod += 2
    if "painted" in target.statuses and attacker.category == "drone" and attacker.side == Side.FRIENDLY:
        mod += 2
    return mod


def is_targetable(unit: UnitState) -> bool:
    return not (unit.category == "commander" and unit.embarked_in)


def combat_profile(battle: BattleState, unit: UnitState) -> UnitState:
    """While embarked, the commander fights with the support drone's profile."""
    if unit.category == "commander" and unit.embarked_in:
        drone = battle.units.get(unit.embarked_in)
        if drone and drone.alive:
            return drone
    return unit


def signal_radius(commander: UnitState) -> int:
    """Fixed command network reach — never reduced by spent RAM."""
    if commander.signal_range is not None:
        return commander.signal_range
    cap = commander.ram_capacity or 6
    return 2 * cap


def unit_within_radius(origin: Hex, unit: UnitState, radius: int) -> bool:
    living = list(unit.living_models)
    if living:
        return any(axial_distance(origin, unit.model_position(m)) <= radius for m in living)
    return axial_distance(origin, unit.position) <= radius


def in_signal(battle: BattleState, unit: UnitState) -> bool:
    if unit.category == "commander":
        return True
    cmd = commander_for_side(battle, unit.side)
    if not cmd or not cmd.alive:
        return unit.category != "drone"
    if unit.category != "drone":
        return True
    return unit_within_radius(cmd.position, unit, signal_radius(cmd))


def evaluate_terminal(battle: BattleState) -> BattleStatus | None:
    cmd = battle.commander()
    opp_cmd = commander_for_side(battle, Side.OPPOSITION)
    opp_alive = battle.living_units(Side.OPPOSITION)
    if cmd is None or not cmd.alive:
        if not opp_alive:
            return BattleStatus.DRAW
        return BattleStatus.DEFEAT
    if opp_cmd is None or not opp_cmd.alive:
        return BattleStatus.VICTORY
    vp_to_win = int(getattr(battle, "vp_to_win", 5) or 5)
    if int(getattr(battle, "friendly_vp", 0) or 0) >= vp_to_win:
        return BattleStatus.VICTORY
    if int(getattr(battle, "opposition_vp", 0) or 0) >= vp_to_win:
        return BattleStatus.DEFEAT
    if not opp_alive:
        return BattleStatus.VICTORY
    return None


def snapshot_unit(u: UnitState, battle: BattleState) -> dict[str, Any]:
    return {
        "unit_instance_id": u.unit_instance_id,
        "definition_id": u.definition_id,
        "display_name": u.display_name,
        "side": u.side.value,
        "category": u.category,
        "roles": u.roles,
        "position": u.position.to_dict(),
        "alive": u.alive,
        "model_count": len(u.models),
        "living_model_count": len(u.living_models),
        "total_hp": u.total_hp,
        "models": [
            {
                "model_id": m.model_id,
                "hp": m.hp,
                "max_hp": m.max_hp,
                "alive": m.alive,
                "position": m.position.to_dict() if m.position is not None else None,
            }
            for m in u.models
        ],
        "leader_model_id": (u.leader_model().model_id if u.leader_model() else None),
        "effective_stats": {
            "speed": u.speed,
            "attack": u.attack,
            "defense": u.defense,
            "armor": u.armor,
        },
        "weapons": u.weapons,
        "abilities": u.abilities,
        "statuses": u.statuses,
        "ammo": u.ammo,
        "is_decoy": u.category == "decoy",
        "signal_state": "in_signal" if in_signal(battle, u) else "out_of_signal",
        "activation_state": "active" if (battle.activation and battle.activation.actor_id == u.unit_instance_id) else (
            "done" if u.activated_this_round else "waiting"
        ),
        "asset_set_id": u.asset_set_id,
        "ram_current": u.ram_current,
        "ram_capacity": u.ram_capacity,
        "signal_range": signal_radius(u) if u.category == "commander" else None,
        "movement_traits": u.movement_traits,
        "size_class": u.size_class,
        "embarked_in": u.embarked_in,
        "embarked_commander_id": u.embarked_commander_id,
        "allocated_ram": int(u.allocated_ram or 0),
        "ram_allocation_cap": (
            1 if (u.size_class or "").lower() == "small" else 3
        )
        if u.category == "drone"
        else None,
    }


def battle_snapshot(battle: BattleState, legal_options: list[dict] | None = None) -> dict[str, Any]:
    from .control_phase import control_phase_snapshot
    from .mines import mines_for_snapshot
    from .objective import objective_snapshot

    cmd = battle.commander()
    return {
        "battle_id": battle.battle_id,
        "session_id": battle.session_id,
        "status": battle.status.value,
        "result": battle.result,
        "state_version": battle.state_version,
        "content_version": battle.content_version,
        "seed": battle.seed,
        "mode": battle.mode,
        "mission": battle.mission_id,
        "point_cap": battle.point_cap,
        "round": battle.round,
        "active_activation_id": battle.activation.activation_id if battle.activation else None,
        "active_actor_id": battle.activation.actor_id if battle.activation else None,
        "actions": battle.activation.actions.to_dict() if battle.activation else None,
        "initiative": [
            {
                "unit_instance_id": uid,
                "display_name": battle.units[uid].display_name if uid in battle.units else uid,
                "side": battle.units[uid].side.value if uid in battle.units else None,
                "activated": battle.units[uid].activated_this_round if uid in battle.units else False,
            }
            for uid in battle.initiative
        ],
        "map": {
            "map_id": battle.map_id,
            "width": battle.width,
            "height": battle.height,
            "terrain": [{"q": int(k.split(",")[0]), "r": int(k.split(",")[1]), "terrain_id": v} for k, v in battle.terrain.items()],
            "ground_asset": get_catalog().maps[battle.map_id].ground_asset if battle.map_id in get_catalog().maps else None,
        },
        "commander": snapshot_unit(cmd, battle) if cmd else None,
        "friendly_units": [snapshot_unit(u, battle) for u in battle.units.values() if u.side == Side.FRIENDLY],
        "opposition_units": [snapshot_unit(u, battle) for u in battle.units.values() if u.side == Side.OPPOSITION],
        "directives": battle.directives,
        "legal_player_options": legal_options or [],
        "pending_confirmation": None,
        "communications_cursor": len(battle.communications),
        "last_event_sequence": battle.event_sequence,
        "signal_radius": signal_radius(cmd) if cmd else 0,
        "commander_avatar": battle.commander_avatar,
        "loadout_id": battle.loadout_id,
        "ram_abilities": battle.ram_abilities,
        "opposition_ram_abilities": getattr(battle, "opposition_ram_abilities", []) or [],
        "field_effects": [
            {
                "effect_id": fx.effect_id,
                "effect_type": fx.effect_type,
                "center": fx.center.to_dict(),
                "radius": fx.radius,
                "rounds_remaining": fx.rounds_remaining,
                "side": fx.side.value,
            }
            for fx in battle.field_effects
        ],
        "mines": mines_for_snapshot(battle, Side.FRIENDLY),
        "objective": objective_snapshot(battle),
        "control_phase": control_phase_snapshot(battle),
    }
