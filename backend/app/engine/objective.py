"""Objective scoring: zone control and capture-the-flags."""

from __future__ import annotations

from ..domain.enums import BattleStatus, Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance
from .scenarios import OBJECTIVE_RADIUS, VP_TO_WIN, is_flag_scenario
from .state import BattleState, UnitState


def _zones(battle: BattleState) -> list[dict]:
    zones = getattr(battle, "objective_zones", None) or []
    if zones:
        return zones
    return [{"id": "center", "label": "Center", "q": battle.width // 2, "r": battle.height // 2, "radius": OBJECTIVE_RADIUS}]


def _radius(battle: BattleState, zone: dict | None = None) -> int:
    if zone and zone.get("radius"):
        return int(zone["radius"])
    return int(getattr(battle, "objective_radius", OBJECTIVE_RADIUS) or OBJECTIVE_RADIUS)


def zone_hex(zone: dict) -> Hex:
    return Hex(int(zone["q"]), int(zone["r"]))


def objective_hex(battle: BattleState) -> Hex:
    zones = _zones(battle)
    center = next((z for z in zones if z.get("id") == "center"), zones[0])
    return zone_hex(center)


def hex_in_zone(battle: BattleState, hex_pos: Hex, zone: dict) -> bool:
    return axial_distance(hex_pos, zone_hex(zone)) <= _radius(battle, zone)


def hex_in_objective(battle: BattleState, hex_pos: Hex) -> bool:
    return any(hex_in_zone(battle, hex_pos, z) for z in _zones(battle))


def unit_in_zone(battle: BattleState, unit: UnitState, zone: dict) -> bool:
    if not unit.alive or unit.category == "decoy":
        return False
    living = list(unit.living_models)
    if living:
        return any(hex_in_zone(battle, unit.model_position(m), zone) for m in living)
    return hex_in_zone(battle, unit.position, zone)


def unit_contests_objective(battle: BattleState, unit: UnitState) -> bool:
    return any(unit_in_zone(battle, unit, z) for z in _zones(battle))


def zone_contesting_units(battle: BattleState, zone: dict, side: Side) -> list[UnitState]:
    return [u for u in battle.living_units(side) if unit_in_zone(battle, u, zone)]


def zone_control(battle: BattleState, zone: dict) -> str:
    friendly = bool(zone_contesting_units(battle, zone, Side.FRIENDLY))
    opposition = bool(zone_contesting_units(battle, zone, Side.OPPOSITION))
    if friendly and opposition:
        return "contested"
    if friendly:
        return "friendly"
    if opposition:
        return "opposition"
    return "empty"


def contesting_units(battle: BattleState, side: Side) -> list[UnitState]:
    return [u for u in battle.living_units(side) if unit_contests_objective(battle, u)]


def current_control(battle: BattleState) -> str:
    """Aggregate control for primary/center zone (HUD compat)."""
    zones = _zones(battle)
    primary = next((z for z in zones if z.get("id") == "center"), zones[0])
    return zone_control(battle, primary)


def _flags(battle: BattleState) -> list[dict]:
    return list(getattr(battle, "flags", None) or [])


def flag_position(battle: BattleState, flag: dict) -> Hex:
    holder_id = flag.get("holder_unit_id")
    if holder_id and holder_id in battle.units:
        u = battle.units[holder_id]
        if u.alive:
            return u.model_position(u.leader_model())
    return Hex(int(flag["q"]), int(flag["r"]))


def flags_held_by(battle: BattleState, side: Side) -> list[dict]:
    out: list[dict] = []
    for flag in _flags(battle):
        holder_id = flag.get("holder_unit_id")
        if not holder_id or holder_id not in battle.units:
            continue
        u = battle.units[holder_id]
        if u.alive and u.side == side:
            out.append(flag)
    return out


def unit_can_grab_flag(battle: BattleState, unit: UnitState, flag: dict) -> bool:
    if not unit.alive or unit.category == "decoy" or unit.category == "commander":
        return False
    if flag.get("holder_unit_id"):
        return False
    pos = unit.model_position(unit.leader_model())
    spawn = Hex(int(flag["spawn_q"]), int(flag["spawn_r"]))
    zone = next((z for z in _zones(battle) if z["id"] == flag["flag_id"]), None)
    radius = _radius(battle, zone) if zone else OBJECTIVE_RADIUS
    return axial_distance(pos, spawn) <= radius


def grab_flag_options(battle: BattleState, unit: UnitState) -> list[dict]:
    if not is_flag_scenario(getattr(battle, "scenario_id", "")):
        return []
    opts: list[dict] = []
    for flag in _flags(battle):
        if unit_can_grab_flag(battle, unit, flag):
            opts.append(flag)
    return opts


def resolve_grab_flag(battle: BattleState, unit: UnitState, flag_id: str) -> list[DomainEvent]:
    flag = next((f for f in _flags(battle) if f["flag_id"] == flag_id), None)
    if not flag or not unit_can_grab_flag(battle, unit, flag):
        raise ValueError("Cannot grab that flag")
    flag["holder_unit_id"] = unit.unit_instance_id
    flag["side"] = unit.side.value
    pos = unit.model_position(unit.leader_model())
    flag["q"] = pos.q
    flag["r"] = pos.r
    label = flag.get("label", flag_id)
    side_name = "Blue" if unit.side == Side.FRIENDLY else "Red"
    radio = f"{side_name} grabbed the {label} flag."
    battle.communications.append({"speaker": "Tactical", "side": "system", "text": radio, "unit_id": unit.unit_instance_id})
    return [
        DomainEvent(
            type="flag_captured",
            actor_id=unit.unit_instance_id,
            payload={
                "flag_id": flag_id,
                "side": unit.side.value,
                "unit_id": unit.unit_instance_id,
                "at": pos.to_dict(),
                "radio": radio,
            },
        )
    ]


def drop_flags_for_unit(battle: BattleState, unit_id: str) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    u = battle.units.get(unit_id)
    drop_at = u.model_position(u.leader_model()) if u and u.alive else None
    for flag in _flags(battle):
        if flag.get("holder_unit_id") != unit_id:
            continue
        if drop_at:
            flag["q"] = drop_at.q
            flag["r"] = drop_at.r
        flag["holder_unit_id"] = None
        flag["side"] = None
        events.append(
            DomainEvent(
                type="flag_dropped",
                payload={"flag_id": flag["flag_id"], "at": {"q": flag["q"], "r": flag["r"]}},
            )
        )
    return events


def sync_flag_positions(battle: BattleState) -> None:
    for flag in _flags(battle):
        holder_id = flag.get("holder_unit_id")
        if not holder_id or holder_id not in battle.units:
            continue
        u = battle.units[holder_id]
        if not u.alive:
            continue
        pos = u.model_position(u.leader_model())
        flag["q"] = pos.q
        flag["r"] = pos.r


def objective_snapshot(battle: BattleState) -> dict:
    meta = getattr(battle, "scenario_meta", None) or {}
    scenario_id = getattr(battle, "scenario_id", "point_control") or "point_control"
    zones_out: list[dict] = []
    for z in _zones(battle):
        zones_out.append(
            {
                "id": z["id"],
                "label": z.get("label", z["id"]),
                "hex": {"q": z["q"], "r": z["r"]},
                "radius": _radius(battle, z),
                "control": zone_control(battle, z),
                "friendly_contesting": [u.unit_instance_id for u in zone_contesting_units(battle, z, Side.FRIENDLY)],
                "opposition_contesting": [u.unit_instance_id for u in zone_contesting_units(battle, z, Side.OPPOSITION)],
            }
        )
    flags_out: list[dict] = []
    for f in _flags(battle):
        flags_out.append(
            {
                "flag_id": f["flag_id"],
                "label": f.get("label", f["flag_id"]),
                "hex": {"q": f["q"], "r": f["r"]},
                "spawn_hex": {"q": f["spawn_q"], "r": f["spawn_r"]},
                "holder_unit_id": f.get("holder_unit_id"),
                "side": f.get("side"),
            }
        )
    primary = zones_out[0] if zones_out else {"hex": objective_hex(battle).to_dict(), "control": "empty"}
    return {
        "type": scenario_id,
        "scenario_id": scenario_id,
        "label": meta.get("display_name", "Objective"),
        "description": meta.get("description", ""),
        "hex": primary["hex"],
        "radius": primary.get("radius", _radius(battle)),
        "zones": zones_out,
        "flags": flags_out,
        "friendly_vp": int(getattr(battle, "friendly_vp", 0) or 0),
        "opposition_vp": int(getattr(battle, "opposition_vp", 0) or 0),
        "vp_to_win": int(getattr(battle, "vp_to_win", VP_TO_WIN) or VP_TO_WIN),
        "control": primary.get("control", current_control(battle)),
        "friendly_contesting": primary.get("friendly_contesting", []),
        "opposition_contesting": primary.get("opposition_contesting", []),
    }


def score_objective_at_round_end(battle: BattleState) -> list[DomainEvent]:
    from .state import evaluate_terminal

    sync_flag_positions(battle)
    scenario_id = getattr(battle, "scenario_id", "point_control") or "point_control"
    friendly_gain = 0
    opposition_gain = 0
    zone_results: list[dict] = []

    if is_flag_scenario(scenario_id):
        friendly_gain = len(flags_held_by(battle, Side.FRIENDLY))
        opposition_gain = len(flags_held_by(battle, Side.OPPOSITION))
        for flag in _flags(battle):
            holder = flag.get("holder_unit_id")
            side = flag.get("side")
            zone_results.append({"flag_id": flag["flag_id"], "holder_unit_id": holder, "side": side})
    else:
        for zone in _zones(battle):
            control = zone_control(battle, zone)
            scored_side = None
            if control == "friendly":
                friendly_gain += 1
                scored_side = "friendly"
            elif control == "opposition":
                opposition_gain += 1
                scored_side = "opposition"
            zone_results.append(
                {
                    "zone_id": zone["id"],
                    "label": zone.get("label", zone["id"]),
                    "control": control,
                    "scored_side": scored_side,
                    "hex": {"q": zone["q"], "r": zone["r"]},
                }
            )

    if friendly_gain:
        battle.friendly_vp = int(getattr(battle, "friendly_vp", 0) or 0) + friendly_gain
    if opposition_gain:
        battle.opposition_vp = int(getattr(battle, "opposition_vp", 0) or 0) + opposition_gain

    friendly_vp = int(getattr(battle, "friendly_vp", 0) or 0)
    opposition_vp = int(getattr(battle, "opposition_vp", 0) or 0)
    meta = getattr(battle, "scenario_meta", {}) or {}
    name = meta.get("display_name", "Objective")

    if friendly_gain or opposition_gain:
        radio = f"{name}: Blue +{friendly_gain}, Red +{opposition_gain}. Score {friendly_vp}–{opposition_vp}."
    else:
        radio = f"{name}: no score this round. {friendly_vp}–{opposition_vp}."

    battle.communications.append({"speaker": "Tactical", "side": "system", "text": radio, "unit_id": None})
    events: list[DomainEvent] = [
        DomainEvent(
            type="objective_scored",
            payload={
                "round": battle.round,
                "scenario_id": scenario_id,
                "friendly_gain": friendly_gain,
                "opposition_gain": opposition_gain,
                "friendly_vp": friendly_vp,
                "opposition_vp": opposition_vp,
                "vp_to_win": int(getattr(battle, "vp_to_win", VP_TO_WIN) or VP_TO_WIN),
                "zones": zone_results,
                "radio": radio,
            },
        )
    ]
    terminal = evaluate_terminal(battle)
    if terminal:
        battle.status = terminal
        battle.result = terminal.value
        events.append(
            DomainEvent(
                type="battle_completed",
                payload={
                    "status": terminal.value,
                    "result": terminal.value,
                    "reason": "objective",
                    "friendly_vp": battle.friendly_vp,
                    "opposition_vp": battle.opposition_vp,
                },
            )
        )
    return events
