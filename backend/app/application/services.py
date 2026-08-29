"""Application use cases: sessions, deploy, commands, simulation."""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ..agents.orchestration import run_agent_activation
from ..config import settings
from ..content.loader import get_catalog
from ..domain.enums import ActionType, BattleStatus, SessionStatus, Side
from ..engine.battle import create_battle, end_activation, execute_option, validate_army
from ..engine.options import build_options, fallback_select, list_reachable, make_move_option
from ..engine.state import BattleState, battle_snapshot, in_signal
from ..persistence.models import DomainEventRow, OutboxRow, SessionRow
from ..telemetry.logging import set_trace_context, structured_log, trace_id_var

# Re-export for API layer
__all__ = ["battle_snapshot"]


# In-process battle store keyed by battle_id (projection also in DB)
_BATTLES: dict[str, BattleState] = {}


def _encode_rng_state(state) -> list | None:
    if state is None:
        return None
    # random.getstate() -> (3, tuple[int...], None)
    version, internal, gauss = state
    return [version, list(internal), gauss]


def _decode_rng_state(data):
    if not data:
        return None
    version, internal, gauss = data
    return (version, tuple(internal), gauss)


def _serialize_battle(battle: BattleState) -> dict:
    # Lightweight pickle-alternative via snapshot + internal fields
    from dataclasses import asdict

    def unit_dict(u):
        return {
            "unit_instance_id": u.unit_instance_id,
            "definition_id": u.definition_id,
            "display_name": u.display_name,
            "side": u.side.value,
            "category": u.category,
            "roles": u.roles,
            "asset_set_id": u.asset_set_id,
            "position": u.position.to_dict(),
            "speed": u.speed,
            "attack": u.attack,
            "defense": u.defense,
            "armor": u.armor,
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
            "weapons": u.weapons,
            "abilities": u.abilities,
            "movement_traits": u.movement_traits,
            "size_class": u.size_class,
            "statuses": u.statuses,
            "ammo": u.ammo,
            "alive": u.alive,
            "activated_this_round": u.activated_this_round,
            "ram_current": u.ram_current,
            "ram_capacity": u.ram_capacity,
            "signal_range": u.signal_range,
            "used_once_abilities": u.used_once_abilities,
            "embarked_in": u.embarked_in,
            "embarked_commander_id": u.embarked_commander_id,
            "allocated_ram": int(u.allocated_ram or 0),
        }

    data = {
        "battle_id": battle.battle_id,
        "session_id": battle.session_id,
        "seed": battle.seed,
        "content_version": battle.content_version,
        "status": battle.status.value,
        "result": battle.result,
        "mode": battle.mode,
        "mission_id": battle.mission_id,
        "point_cap": battle.point_cap,
        "map_id": battle.map_id,
        "width": battle.width,
        "height": battle.height,
        "round": battle.round,
        "state_version": battle.state_version,
        "event_sequence": battle.event_sequence,
        "terrain": battle.terrain,
        "units": {k: unit_dict(v) for k, v in battle.units.items()},
        "initiative": battle.initiative,
        "initiative_index": battle.initiative_index,
        "activation": None
        if not battle.activation
        else {
            "activation_id": battle.activation.activation_id,
            "actor_id": battle.activation.actor_id,
            "actions": battle.activation.actions.to_dict(),
            "options": battle.activation.options,
        },
        "directives": battle.directives,
        "communications": battle.communications,
        "events": battle.events,
        "rng_index": battle.rng_index,
        "rng_state": _encode_rng_state(battle.rng_state),
        "commander_avatar": battle.commander_avatar,
        "loadout_id": battle.loadout_id,
        "ram_abilities": battle.ram_abilities,
        "opposition_ram_abilities": getattr(battle, "opposition_ram_abilities", []) or [],
        "friendly_vp": getattr(battle, "friendly_vp", 0),
        "opposition_vp": getattr(battle, "opposition_vp", 0),
        "vp_to_win": getattr(battle, "vp_to_win", 5),
        "objective_radius": getattr(battle, "objective_radius", 5),
        "scenario_id": getattr(battle, "scenario_id", "point_control"),
        "objective_type": getattr(battle, "objective_type", "zone_control"),
        "objective_zones": getattr(battle, "objective_zones", []),
        "flags": getattr(battle, "flags", []),
        "scenario_meta": getattr(battle, "scenario_meta", {}),
        "field_effects": [
            {
                "effect_id": fx.effect_id,
                "effect_type": fx.effect_type,
                "center": fx.center.to_dict(),
                "radius": fx.radius,
                "rounds_remaining": fx.rounds_remaining,
                "side": fx.side.value,
                "source_unit_id": fx.source_unit_id,
            }
            for fx in battle.field_effects
        ],
        "mines": [
            {
                "mine_id": m.mine_id,
                "position": m.position.to_dict(),
                "side": m.side.value,
                "damage": m.damage,
                "area": m.area,
                "revealed": m.revealed,
                "armed": m.armed,
                "source_unit_id": m.source_unit_id,
            }
            for m in battle.mines
        ],
        "support_drone_unit_id": battle.support_drone_unit_id,
        "control_phase": None
        if not battle.control_phase
        else {
            "active": bool(battle.control_phase.active),
            "side": battle.control_phase.side.value,
            "commander_id": battle.control_phase.commander_id,
        },
    }
    return data


def _deserialize_battle(data: dict) -> BattleState:
    from ..domain.hex import Hex
    from ..engine.state import ActionPool, ActivationState, ModelState, UnitState

    battle = BattleState(
        battle_id=data["battle_id"],
        session_id=data["session_id"],
        seed=data["seed"],
        content_version=data["content_version"],
        status=BattleStatus(data["status"]),
        result=data.get("result"),
        mode=data["mode"],
        mission_id=data["mission_id"],
        point_cap=data["point_cap"],
        map_id=data["map_id"],
        width=data["width"],
        height=data["height"],
        round=data["round"],
        state_version=data["state_version"],
        event_sequence=data["event_sequence"],
        terrain=data["terrain"],
        initiative=data["initiative"],
        initiative_index=data["initiative_index"],
        directives=data.get("directives", []),
        communications=data.get("communications", []),
        events=data.get("events", []),
        rng_index=data["rng_index"],
        rng_state=_decode_rng_state(data.get("rng_state")),
        commander_avatar=data.get("commander_avatar", "male"),
        loadout_id=data.get("loadout_id") or data.get("commander_avatar", "male"),
        ram_abilities=data.get("ram_abilities", []),
        opposition_ram_abilities=data.get("opposition_ram_abilities", []),
        friendly_vp=int(data.get("friendly_vp", 0) or 0),
        opposition_vp=int(data.get("opposition_vp", 0) or 0),
        vp_to_win=int(data.get("vp_to_win", 5) or 5),
        objective_radius=int(data.get("objective_radius", 5) or 5),
        scenario_id=data.get("scenario_id", "point_control") or "point_control",
        objective_type=data.get("objective_type", "zone_control") or "zone_control",
        objective_zones=list(data.get("objective_zones", []) or []),
        flags=list(data.get("flags", []) or []),
        scenario_meta=dict(data.get("scenario_meta", {}) or {}),
    )
    from ..engine.state import ControlPhaseState, FieldEffect, MineState

    for fx in data.get("field_effects", []):
        c = fx["center"]
        battle.field_effects.append(
            FieldEffect(
                effect_id=fx["effect_id"],
                effect_type=fx["effect_type"],
                center=Hex(c["q"], c["r"]),
                radius=int(fx["radius"]),
                rounds_remaining=int(fx["rounds_remaining"]),
                side=Side(fx["side"]),
                source_unit_id=fx.get("source_unit_id", ""),
            )
        )
    for md in data.get("mines", []):
        p = md["position"]
        battle.mines.append(
            MineState(
                mine_id=md["mine_id"],
                position=Hex(p["q"], p["r"]),
                side=Side(md["side"]),
                damage=int(md.get("damage", 10) or 10),
                area=int(md.get("area", 1) or 1),
                revealed=bool(md.get("revealed", False)),
                armed=bool(md.get("armed", True)),
                source_unit_id=md.get("source_unit_id", ""),
            )
        )
    battle.support_drone_unit_id = data.get("support_drone_unit_id")
    cp = data.get("control_phase")
    if cp and cp.get("active"):
        battle.control_phase = ControlPhaseState(
            active=True,
            side=Side(cp["side"]),
            commander_id=str(cp.get("commander_id") or ""),
        )
    else:
        battle.control_phase = None
    for uid, ud in data["units"].items():
        models = []
        for m in ud["models"]:
            pos = m.get("position")
            models.append(
                ModelState(
                    model_id=m["model_id"],
                    hp=m["hp"],
                    max_hp=m["max_hp"],
                    alive=m.get("alive", True),
                    position=Hex(pos["q"], pos["r"]) if pos else None,
                )
            )
        # Back-compat: older saves without model positions
        unit_pos = Hex(ud["position"]["q"], ud["position"]["r"])
        if all(m.position is None for m in models):
            for m in models:
                if m.alive:
                    m.position = unit_pos
        battle.units[uid] = UnitState(
            unit_instance_id=ud["unit_instance_id"],
            definition_id=ud["definition_id"],
            display_name=ud["display_name"],
            side=Side(ud["side"]),
            category=ud["category"],
            roles=ud["roles"],
            asset_set_id=ud["asset_set_id"],
            position=unit_pos,
            speed=ud["speed"],
            attack=ud["attack"],
            defense=ud["defense"],
            armor=ud["armor"],
            models=models,
            weapons=ud["weapons"],
            abilities=ud["abilities"],
            movement_traits=ud["movement_traits"],
            size_class=str(ud.get("size_class") or "medium"),
            statuses=ud.get("statuses", []),
            ammo=ud.get("ammo", {}),
            alive=ud["alive"],
            activated_this_round=ud.get("activated_this_round", False),
            ram_current=ud.get("ram_current"),
            ram_capacity=ud.get("ram_capacity"),
            signal_range=ud.get("signal_range"),
            used_once_abilities=ud.get("used_once_abilities", []),
            embarked_in=ud.get("embarked_in"),
            embarked_commander_id=ud.get("embarked_commander_id"),
            allocated_ram=int(ud.get("allocated_ram", 0) or 0),
        )
        battle.units[uid].sync_position_from_leader()
    act = data.get("activation")
    if act:
        raw_actions = dict(act.get("actions") or {})
        if not raw_actions:
            pool = ActionPool()
        else:
            standard = int(raw_actions["standard"]) if "standard" in raw_actions else 1
            move = int(raw_actions["move"]) if "move" in raw_actions else 1
            minor = int(raw_actions["minor"]) if "minor" in raw_actions else 1
            if "moves_spent" in raw_actions:
                moves_spent = int(raw_actions["moves_spent"] or 0)
            else:
                # Legacy saves: infer so a spent Move cannot be forgotten across requests
                moves_spent = 0
                if move < 1:
                    moves_spent = 1 if standard >= 1 else 2
            pool = ActionPool(standard=standard, move=move, minor=minor, moves_spent=moves_spent)
        battle.activation = ActivationState(
            activation_id=act["activation_id"],
            actor_id=act["actor_id"],
            actions=pool,
            options=act.get("options") or {},
        )
    return battle


def get_battle(battle_id: str) -> BattleState | None:
    if battle_id in _BATTLES:
        return _BATTLES[battle_id]
    return None


def persist_battle(db: Session, row: SessionRow, battle: BattleState) -> None:
    _BATTLES[battle.battle_id] = battle
    row.battle_id = battle.battle_id
    row.battle_json = _serialize_battle(battle)
    row.state_version = battle.state_version
    row.last_trace_id = trace_id_var.get()
    set_trace_context(session_id=battle.session_id, battle_id=battle.battle_id)

    existing_seq = {
        seq
        for (seq,) in db.query(DomainEventRow.sequence).filter(DomainEventRow.battle_id == battle.battle_id).all()
    }
    for env in battle.events:
        seq = int(env["sequence"])
        if seq in existing_seq:
            continue
        db.add(
            DomainEventRow(
                session_id=battle.session_id,
                battle_id=battle.battle_id,
                sequence=seq,
                event_type=str(env.get("type", "")),
                state_version=int(env.get("state_version") or battle.state_version),
                envelope_json=env,
            )
        )
        db.add(
            OutboxRow(
                session_id=battle.session_id,
                battle_id=battle.battle_id,
                event_sequence=seq,
                payload_json={"type": env.get("type"), "sequence": seq, "state_version": env.get("state_version")},
                status="published",
            )
        )
    db.commit()
    structured_log(
        "battle_persisted",
        session_id=battle.session_id,
        battle_id=battle.battle_id,
        state_version=battle.state_version,
        event_count=len(battle.events),
        status=battle.status.value,
        round=battle.round,
    )


def load_battle_from_row(row: SessionRow) -> BattleState | None:
    if not row.battle_json:
        return None
    battle = _deserialize_battle(row.battle_json)
    _BATTLES[battle.battle_id] = battle
    return battle


def create_session(db: Session) -> dict:
    catalog = get_catalog()
    sid = str(uuid4())
    row = SessionRow(
        session_id=sid,
        status=SessionStatus.DRAFT.value,
        content_version=catalog.content_version,
        prep_json={
            "avatar": "male",
            "loadout_id": "male",
            "ram_abilities": ["defense_matrix", "call_for_action", "targeting_assistance"],
            "mode": "freestyle_vs",
            "mission_id": "freestyle_vs_15",
            "point_cap": 15,
            "army": [{"definition_id": "friendly_infantry_squad", "count": 1}],
        },
        command_receipts={},
    )
    db.add(row)
    db.commit()
    structured_log("session_created", session_id=sid, content_version=catalog.content_version)
    return session_snapshot(row)


def session_snapshot(row: SessionRow) -> dict:
    battle_summary = None
    if row.battle_id and row.battle_json:
        battle_summary = {
            "battle_id": row.battle_id,
            "status": row.battle_json.get("status"),
            "round": row.battle_json.get("round"),
            "result": row.battle_json.get("result"),
        }
    return {
        "session_id": row.session_id,
        "session_status": row.status,
        "generation": row.generation,
        "state_version": row.state_version,
        "content_version": row.content_version,
        "prep": row.prep_json,
        "battle_summary": battle_summary,
        "allowed_commands": _allowed(row),
    }


def _allowed(row: SessionRow) -> list[str]:
    if row.status == SessionStatus.DRAFT.value:
        return ["update_prep", "deploy", "reset"]
    if row.status == SessionStatus.ACTIVE.value:
        return ["commander_action", "end_activation", "directive", "abort", "reset"]
    return ["reset", "feedback"]


def update_prep(db: Session, row: SessionRow, prep: dict, command_id: str) -> dict:
    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    row.prep_json = prep
    row.state_version += 1
    result = session_snapshot(row)
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    db.commit()
    return result


def deploy(db: Session, row: SessionRow, command_id: str, seed: int | None = None) -> dict:
    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if row.status != SessionStatus.DRAFT.value and row.battle_id:
        # Idempotent: return existing
        battle = load_battle_from_row(row) or get_battle(row.battle_id)
        snap = player_snapshot(battle)
        return {"session": session_snapshot(row), "battle": snap}

    errors = validate_army(row.prep_json)
    if errors:
        raise ValueError("; ".join(errors))

    set_trace_context(session_id=row.session_id)
    battle = create_battle(row.session_id, row.prep_json, seed=seed)
    row.status = SessionStatus.ACTIVE.value
    structured_log(
        "battle_deployed",
        session_id=row.session_id,
        battle_id=battle.battle_id,
        seed=battle.seed,
        point_cap=battle.point_cap,
        command_id=command_id,
    )
    persist_battle(db, row, battle)
    advance_agents(db, row, battle)
    snap = player_snapshot(battle)
    result = {"session": session_snapshot(row), "battle": snap}
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    db.commit()
    return result


def _legal_for_player(battle: BattleState) -> list[dict]:
    """Player option menu: hold / attack / RAM. Moves use reachable_hexes + move_to."""
    if not battle.activation:
        return []
    unit = battle.units.get(battle.activation.actor_id)
    if not unit or unit.category != "commander" or unit.side != Side.FRIENDLY:
        return []
    from ..engine.control_phase import control_phase_blocks_commander_actions

    if control_phase_blocks_commander_actions(battle):
        return []
    # sample_moves=0: do not enumerate move destinations in the option list
    battle.activation.options = build_options(get_catalog(), battle, unit, sample_moves=0)
    return list(battle.activation.options.values())


def _enrich_player_snapshot(battle: BattleState, snap: dict) -> dict:
    """Attach full reachable hexes and second-move cue for commander UI."""
    snap = dict(snap)
    reachable: list[dict] = []
    second_move = False
    from ..engine.control_phase import control_phase_blocks_commander_actions

    if battle.activation and not control_phase_blocks_commander_actions(battle):
        unit = battle.units.get(battle.activation.actor_id)
        if unit and unit.category == "commander" and unit.side == Side.FRIENDLY:
            reachable = list_reachable(get_catalog(), battle, unit)
            actions = battle.activation.actions
            second_move = (
                actions.moves_spent >= 1
                and actions.moves_spent < 2
                and actions.standard >= 1
                and actions.can_spend(ActionType.MOVE)
            )
    snap["reachable_hexes"] = reachable
    snap["second_move_costs_attack"] = second_move
    return snap


def player_snapshot(battle: BattleState) -> dict:
    return _enrich_player_snapshot(battle, battle_snapshot(battle, _legal_for_player(battle)))


def advance_agents(db: Session, row: SessionRow, battle: BattleState, max_steps: int = 40) -> None:
    """Run agent activations until player commander or battle ends."""
    steps = 0
    while battle.status == BattleStatus.ACTIVE and battle.activation and steps < max_steps:
        unit = battle.units[battle.activation.actor_id]
        if unit.category == "commander" and unit.side == Side.FRIENDLY:
            break
        run_agent_activation(battle, db=db)
        steps += 1
        # Commit agent run rows incrementally so crashes still leave diagnostics
        db.commit()
    persist_battle(db, row, battle)


def resolve_next_agent(db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int) -> dict:
    """Run exactly one non-commander activation so the UI can rotate initiative."""
    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if expected_version != battle.state_version:
        raise ConflictError(battle.state_version, player_snapshot(battle))
    if battle.status != BattleStatus.ACTIVE or not battle.activation:
        snap = player_snapshot(battle)
        result = {"battle": snap, "resolved": False, "step_events": []}
        receipts[command_id] = {"result": result}
        row.command_receipts = receipts
        persist_battle(db, row, battle)
        return result
    unit = battle.units[battle.activation.actor_id]
    if unit.category == "commander" and unit.side == Side.FRIENDLY:
        snap = player_snapshot(battle)
        result = {"battle": snap, "resolved": False, "step_events": []}
        receipts[command_id] = {"result": result}
        row.command_receipts = receipts
        persist_battle(db, row, battle)
        return result
    seq_before = battle.event_sequence
    actor_name = unit.display_name
    actor_side = unit.side.value
    run_agent_activation(battle, db=db)
    db.commit()
    step_events = [e for e in battle.events if int(e.get("sequence") or 0) > seq_before]
    snap = player_snapshot(battle)
    if battle.status != BattleStatus.ACTIVE:
        row.status = SessionStatus.ENDED.value
    result = {
        "battle": snap,
        "resolved": True,
        "step_events": step_events,
        "actor_id": unit.unit_instance_id,
        "actor_name": actor_name,
        "actor_side": actor_side,
    }
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


def commander_cast_ram(
    db: Session,
    row: SessionRow,
    battle: BattleState,
    command_id: str,
    expected_version: int,
    ability_id: str,
    *,
    target_unit_id: str | None = None,
    q: int | None = None,
    r: int | None = None,
) -> dict:
    """Cast a RAM ability with explicit targets (spoof, assist, airstrike, etc.)."""
    from ..domain.hex import Hex
    from ..engine.combat import resolve_ram_ability
    from ..engine.options import build_options

    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if expected_version != battle.state_version:
        raise ConflictError(battle.state_version, player_snapshot(battle))
    if not battle.activation:
        raise ValueError("No activation")
    unit = battle.units[battle.activation.actor_id]
    if unit.category != "commander" or unit.side != Side.FRIENDLY:
        raise ValueError("Not commander activation")
    from ..engine.control_phase import control_phase_blocks_commander_actions

    if control_phase_blocks_commander_actions(battle):
        raise ValueError("Complete RAM allocation first")
    if not battle.activation.actions.can_spend(ActionType.MINOR):
        raise ValueError("No minor action remaining")
    target_hex = Hex(q, r) if q is not None and r is not None else None
    seq_before = battle.event_sequence
    events = resolve_ram_ability(
        get_catalog(),
        battle,
        unit,
        ability_id,
        target_hex=target_hex,
        target_unit_id=target_unit_id,
    )
    battle.append_events(events)
    if battle.status == BattleStatus.ACTIVE and battle.activation:
        battle.activation.options = build_options(get_catalog(), battle, unit)
    snap = player_snapshot(battle)
    if battle.status != BattleStatus.ACTIVE:
        row.status = SessionStatus.ENDED.value
    step_events = [e for e in battle.events if int(e.get("sequence") or 0) > seq_before]
    result = {
        "battle": snap,
        "step_events": step_events,
        "actor_id": unit.unit_instance_id,
        "actor_name": unit.display_name,
        "actor_side": unit.side.value,
    }
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


def commander_action(db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int, option_id: str) -> dict:
    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if expected_version != battle.state_version:
        raise ConflictError(battle.state_version, player_snapshot(battle))
    if not battle.activation:
        raise ValueError("No activation")
    unit = battle.units[battle.activation.actor_id]
    if unit.category != "commander":
        raise ValueError("Not commander activation")
    from ..engine.control_phase import control_phase_blocks_commander_actions

    if control_phase_blocks_commander_actions(battle):
        raise ValueError("Complete RAM allocation first")
    seq_before = battle.event_sequence
    execute_option(battle, option_id)
    # Hold ends activation — do not batch agents; client steps via resolve-next
    snap = player_snapshot(battle)
    if battle.status != BattleStatus.ACTIVE:
        row.status = SessionStatus.ENDED.value
    step_events = [e for e in battle.events if int(e.get("sequence") or 0) > seq_before]
    result = {
        "battle": snap,
        "step_events": step_events,
        "actor_id": unit.unit_instance_id,
        "actor_name": unit.display_name,
        "actor_side": unit.side.value,
    }
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


def commander_move_to(
    db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int, q: int, r: int
) -> dict:
    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if expected_version != battle.state_version:
        raise ConflictError(battle.state_version, player_snapshot(battle))
    if not battle.activation:
        raise ValueError("No activation")
    unit = battle.units[battle.activation.actor_id]
    if unit.category != "commander" or unit.side != Side.FRIENDLY:
        raise ValueError("Not commander activation")
    from ..engine.control_phase import control_phase_blocks_commander_actions

    if control_phase_blocks_commander_actions(battle):
        raise ValueError("Complete RAM allocation first")
    seq_before = battle.event_sequence
    opt = make_move_option(get_catalog(), battle, unit, q, r)
    if not battle.activation.options:
        battle.activation.options = {}
    battle.activation.options[opt["option_id"]] = opt
    execute_option(battle, opt["option_id"])
    step_events = [e for e in battle.events if int(e.get("sequence") or 0) > seq_before]
    snap = player_snapshot(battle)
    if battle.status != BattleStatus.ACTIVE:
        row.status = SessionStatus.ENDED.value
    result = {"battle": snap, "step_events": step_events}
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


def commander_end(db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int) -> dict:
    """End current commander activation and return next actor (no agent batch)."""
    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if expected_version != battle.state_version:
        raise ConflictError(battle.state_version, player_snapshot(battle))
    if not battle.activation:
        raise ValueError("No activation")
    unit = battle.units[battle.activation.actor_id]
    if unit.category != "commander" or unit.side != Side.FRIENDLY:
        raise ValueError("Not commander activation")
    from ..engine.control_phase import control_phase_blocks_commander_actions

    if control_phase_blocks_commander_actions(battle):
        raise ValueError("Complete RAM allocation first")
    end_activation(battle)
    snap = player_snapshot(battle)
    if battle.status != BattleStatus.ACTIVE:
        row.status = SessionStatus.ENDED.value
    result = {"battle": snap}
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


def _control_phase_command(
    db: Session,
    row: SessionRow,
    battle: BattleState,
    command_id: str,
    expected_version: int,
    *,
    op: str,
    drone_id: str | None = None,
) -> dict:
    """Side-agnostic Control Phase mutate (player = friendly; Red LLM can reuse later)."""
    from ..engine.control_phase import allocate_ram, complete_control_phase, reclaim_ram

    receipts = row.command_receipts or {}
    if command_id in receipts:
        return receipts[command_id]["result"]
    if expected_version != battle.state_version:
        raise ConflictError(battle.state_version, player_snapshot(battle))
    if not battle.activation:
        raise ValueError("No activation")
    unit = battle.units[battle.activation.actor_id]
    if unit.category != "commander":
        raise ValueError("Not commander activation")
    # Player API today: only friendly commander. Engine itself is side-agnostic.
    if unit.side != Side.FRIENDLY:
        raise ValueError("Not player commander activation")
    seq_before = battle.event_sequence
    if op == "allocate":
        if not drone_id:
            raise ValueError("drone_id required")
        events = allocate_ram(battle, drone_id, actor_side=Side.FRIENDLY)
    elif op == "reclaim":
        if not drone_id:
            raise ValueError("drone_id required")
        events = reclaim_ram(battle, drone_id, actor_side=Side.FRIENDLY)
    elif op == "complete":
        events = complete_control_phase(battle, actor_side=Side.FRIENDLY)
    else:
        raise ValueError(f"Unknown control phase op {op}")
    battle.append_events(events)
    step_events = [e for e in battle.events if int(e.get("sequence") or 0) > seq_before]
    snap = player_snapshot(battle)
    result = {
        "battle": snap,
        "step_events": step_events,
        "actor_id": unit.unit_instance_id,
        "actor_name": unit.display_name,
        "actor_side": unit.side.value,
    }
    receipts[command_id] = {"result": result}
    row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


def control_phase_allocate(
    db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int, drone_id: str
) -> dict:
    return _control_phase_command(
        db, row, battle, command_id, expected_version, op="allocate", drone_id=drone_id
    )


def control_phase_reclaim(
    db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int, drone_id: str
) -> dict:
    return _control_phase_command(
        db, row, battle, command_id, expected_version, op="reclaim", drone_id=drone_id
    )


def control_phase_complete(
    db: Session, row: SessionRow, battle: BattleState, command_id: str, expected_version: int
) -> dict:
    return _control_phase_command(db, row, battle, command_id, expected_version, op="complete")


def _apply_directive_entry(battle: BattleState, entry: dict, unit_id: str | None, comm_text: str) -> None:
    if unit_id:
        battle.directives = [d for d in battle.directives if d.get("target_unit_id") != unit_id]
    else:
        battle.directives = [d for d in battle.directives if d.get("scope") == "unit"]
    battle.directives.append(entry)
    from ..domain.events import DomainEvent

    battle.append_standing_order_events([DomainEvent(type="directive_updated", payload=entry)])
    battle.communications.append(
        {
            "speaker": "Commander",
            "side": "friendly",
            "text": comm_text,
            "unit_id": battle.commander().unit_instance_id if battle.commander() else None,
        }
    )


def _build_directive_entry(
    battle: BattleState,
    *,
    text: str,
    unit_id: str | None,
    order_id: str | None,
    target_refs: list,
) -> tuple[dict, str, str | None]:
    """Validate against the live board and return (entry, comm_text, scoped_unit_id)."""
    catalog = get_catalog()
    derived_tags: list[str] = []
    raw_text = (text or "").strip()
    resolved_order_id = order_id
    scoped_unit_id = unit_id

    if order_id:
        order = catalog.army_orders.get(order_id)
        if not order:
            raise ValueError(f"Unknown army order '{order_id}'")
        derived_tags = list(order.tags)
        if order_id == "custom":
            if not raw_text:
                raise ValueError("Custom order requires text")
        else:
            raw_text = order.raw_text
            if order.requires_target:
                if not target_refs:
                    raise ValueError(f"{order.label} requires a target")
                tid = None
                for ref in target_refs:
                    if isinstance(ref, dict) and ref.get("kind") == "unit":
                        tid = ref.get("unit_instance_id")
                        break
                target = battle.units.get(tid) if tid else None
                if not target or target.side != Side.OPPOSITION or not target.alive:
                    raise ValueError(f"{order.label} target must be a living opposition unit")
                if order_id == "focus_fire":
                    raw_text = f"Focus fire on {target.display_name}."
                elif order_id == "paint_target":
                    raw_text = f"Paint {target.display_name} for Airstrike."
                else:
                    raw_text = f"{order.raw_text} Target: {target.display_name}."
        scoped_unit_id = None
    elif unit_id:
        target = battle.units.get(unit_id)
        if not target or target.side != Side.FRIENDLY:
            raise ValueError("Directive target must be a friendly unit")
        if target.category == "commander":
            raise ValueError("Select a squad or drone for unit directives")
        if target.category == "drone" and not in_signal(battle, target):
            raise ValueError("Drone is out of signal and cannot receive a new directive")
        if not raw_text:
            raise ValueError("Directive text required")
        resolved_order_id = "unit_custom"
    else:
        if not raw_text:
            raise ValueError("Order text required")
        resolved_order_id = "custom"
        derived_tags = ["custom"]

    entry = {
        "directive_id": str(uuid4()),
        "scope": "unit" if scoped_unit_id else "global",
        "target_unit_id": scoped_unit_id,
        "order_id": resolved_order_id,
        "raw_text": raw_text,
        "derived_tags": derived_tags,
        "target_refs": target_refs,
        "issued_round": battle.round,
        "issued_state_version": battle.state_version,
        "active": True,
        "queued": True,
    }
    comm_prefix = "Unit directive" if scoped_unit_id else "Army order"
    return entry, f"{comm_prefix}: {raw_text}", scoped_unit_id


def set_directives(
    db: Session,
    row: SessionRow,
    battle: BattleState,
    text: str,
    unit_id: str | None = None,
    *,
    command_id: str | None = None,
    order_id: str | None = None,
    target_refs: list | None = None,
) -> dict:
    receipts = row.command_receipts or {}
    if command_id and command_id in receipts:
        return receipts[command_id]["result"]
    target_refs = list(target_refs or [])

    # Reload authoritative state so standing orders cannot overwrite an in-flight agent resolve.
    fresh = load_battle_from_row(row)
    if fresh is not None:
        battle = fresh

    entry, comm_text, scoped_unit_id = _build_directive_entry(
        battle,
        text=text,
        unit_id=unit_id,
        order_id=order_id,
        target_refs=target_refs,
    )
    _apply_directive_entry(battle, entry, scoped_unit_id, comm_text)
    result = player_snapshot(battle)
    if command_id:
        receipts[command_id] = {"result": result}
        row.command_receipts = receipts
    persist_battle(db, row, battle)
    return result


class ConflictError(Exception):
    def __init__(self, current_version: int, snapshot: dict):
        self.current_version = current_version
        self.snapshot = snapshot


def run_headless_simulation(seed: int = 42, max_rounds: int = 30) -> dict:
    """Fallback-only full battle for tests."""
    prep = {
        "avatar": "male",
        "loadout_id": "male",
        "ram_abilities": ["defense_matrix", "call_for_action", "targeting_assistance"],
        "mode": "freestyle_vs",
        "mission_id": "freestyle_vs_15",
        "point_cap": 15,
        "army": [
            {"definition_id": "friendly_infantry_squad", "count": 1},
        ],
    }
    # Temporarily force fallback by disabling external LLM via local flag
    old = settings.llm_external_enabled
    settings.llm_external_enabled = False
    try:
        battle = create_battle(str(uuid4()), prep, seed=seed)
        guard = 0
        while battle.status == BattleStatus.ACTIVE and battle.round <= max_rounds and guard < 500:
            guard += 1
            if not battle.activation:
                break
            unit = battle.units[battle.activation.actor_id]
            opts = battle.activation.options or build_options(get_catalog(), battle, unit)
            battle.activation.options = opts
            oid = fallback_select(opts, unit, battle)
            execute_option(battle, oid)
            if battle.status != BattleStatus.ACTIVE:
                break
            if battle.activation and battle.activation.actor_id == unit.unit_instance_id:
                opts2 = build_options(get_catalog(), battle, unit)
                battle.activation.options = opts2
                attack_ids = [k for k, v in opts2.items() if v["subroutine"] == "attack"]
                move_ids = [k for k, v in opts2.items() if v["subroutine"] in ("move", "return_to_signal", "return_to_resupply")]
                if attack_ids and battle.activation.actions.can_spend(ActionType.STANDARD):
                    execute_option(battle, attack_ids[0])
                elif move_ids and battle.activation.actions.can_spend(ActionType.MOVE):
                    # Double-move when no shot is available
                    execute_option(battle, fallback_select(opts2, unit, battle))
                if battle.status != BattleStatus.ACTIVE:
                    break
                if battle.activation and battle.activation.actor_id == unit.unit_instance_id:
                    end_activation(battle)
        return {
            "status": battle.status.value,
            "result": battle.result,
            "round": battle.round,
            "state_version": battle.state_version,
            "event_count": len(battle.events),
            "seed": seed,
            "friendly_alive": len(battle.living_units(Side.FRIENDLY)),
            "opposition_alive": len(battle.living_units(Side.OPPOSITION)),
        }
    finally:
        settings.llm_external_enabled = old
