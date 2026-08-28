"""Battle creation, deployment, initiative, activation advancement."""

from __future__ import annotations

from uuid import uuid4
import secrets

from ..config import settings
from ..content.loader import ContentCatalog, get_catalog
from ..domain.enums import ActionType, BattleStatus, Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance, hex_key, in_bounds
from ..domain.rng import SeededRNG
from .combat import resolve_attack, resolve_paint_target, resolve_ram_ability, resolve_self_destruct
from .field_effects import (
    find_support_drone,
    resolve_call_support_drone,
    resolve_drop_smoke,
    resolve_embarked_drone_destroyed,
    resolve_leave_support_drone,
    try_support_drone_auto_load,
)
from .formation import deploy_formation, plan_squad_move
from .opposition import build_opposition_force
from .options import build_options, fallback_select
from .pathfinding import find_path
from .state import (
    ActionPool,
    ActivationState,
    BattleState,
    ModelState,
    UnitState,
    battle_snapshot,
    commander_for_side,
    evaluate_terminal,
)


DEFAULT_OPPOSITION_RAM_ABILITIES = ["targeting_assistance", "call_for_action", "defense_matrix"]


def _commander_profile_id(catalog: ContentCatalog, prep: dict) -> str:
    """Avatar choice maps 1:1 to commander base stats (formerly separate loadouts)."""
    avatar = prep.get("avatar") or "male"
    if avatar in catalog.loadouts:
        return avatar
    legacy = prep.get("loadout_id")
    if legacy in catalog.loadouts:
        return legacy
    return "male"


def _make_unit(
    catalog: ContentCatalog,
    definition_id: str,
    side: Side,
    position: Hex,
    *,
    loadout_id: str | None = None,
    instance_id: str | None = None,
    commander_avatar: str | None = None,
) -> UnitState:
    udef = catalog.units[definition_id]
    models = [
        ModelState(model_id=f"m{i+1}", hp=udef.hp_per_model, max_hp=udef.hp_per_model, position=position)
        for i in range(udef.model_count)
    ]
    ammo: dict[str, int] = {}
    for wid in udef.weapons:
        w = catalog.weapons[wid]
        if w.ammo is not None:
            ammo[wid] = w.ammo

    speed = udef.speed
    attack = udef.attack
    defense = udef.defense
    armor = udef.armor
    hp = udef.hp_per_model
    ram_current = None
    ram_capacity = None
    signal_range = None
    weapons = list(udef.weapons)
    abilities = list(udef.abilities)

    if udef.category == "commander" and loadout_id:
        loadout = catalog.loadouts[loadout_id]
        speed = loadout.speed
        attack = loadout.attack
        defense = loadout.defense
        armor = loadout.armor
        hp = loadout.hp
        models = [ModelState(model_id="m1", hp=hp, max_hp=hp, position=position)]
        ram_capacity = loadout.ram_capacity
        ram_current = loadout.ram_capacity
        signal_range = 2 * loadout.ram_capacity
        weapons = list(loadout.weapons)
        for wid in weapons:
            w = catalog.weapons[wid]
            if w.ammo is not None:
                ammo[wid] = w.ammo

    display_name = udef.display_name
    if udef.category == "commander" and loadout_id and loadout_id in catalog.loadouts:
        display_name = catalog.loadouts[loadout_id].display_name

    unit = UnitState(
        unit_instance_id=instance_id or str(uuid4()),
        definition_id=definition_id,
        display_name=display_name,
        side=side,
        category=udef.category,
        roles=list(udef.roles),
        asset_set_id=udef.asset_set_id,
        position=position,
        speed=speed,
        attack=attack,
        defense=defense,
        armor=armor,
        models=models,
        weapons=weapons,
        abilities=abilities,
        movement_traits=list(udef.movement_traits),
        size_class=str(getattr(udef, "size_class", None) or "medium"),
        ammo=ammo,
        ram_current=ram_current,
        ram_capacity=ram_capacity,
        signal_range=signal_range,
    )
    # Single-model units stay stacked on the token hex; squads get formation at deploy.
    if not unit.is_multi_model:
        for m in unit.models:
            m.position = position
    return unit


def _deploy_side(
    catalog: ContentCatalog,
    battle: BattleState,
    roster: list[tuple[str, int]],
    side: Side,
    rows: list[int],
    rng: SeededRNG,
    loadout_id: str | None = None,
    id_prefix: str = "u",
    commander_avatar: str | None = None,
) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    cols = list(range(battle.width))
    slots: list[Hex] = []
    for r in rows:
        for q in cols:
            h = Hex(q, r)
            slots.append(h)
    # Cluster the army near the deploy midline so RAM buffs and temple pushes start together
    jitter = rng.next_int(-6, 6)
    anchor = Hex(max(0, min(battle.width - 1, battle.width // 2 + jitter)), rows[len(rows) // 2])
    slots.sort(key=lambda h: (axial_distance(h, anchor), h.q, h.r))
    slot_i = 0
    occ = battle.occupancy()
    seq = 0

    for def_id, count in roster:
        udef = catalog.units[def_id]
        for _ in range(count):
            placed = None
            while slot_i < len(slots):
                h = slots[slot_i]
                slot_i += 1
                if hex_key(h) in occ:
                    continue
                tdef = catalog.terrain.get(battle.terrain_at(h))
                if "flying" in udef.movement_traits:
                    if tdef and tdef.fly_move_cost is None:
                        continue
                else:
                    if tdef and tdef.ground_move_cost is None:
                        continue
                placed = h
                break
            if placed is None:
                placed = Hex(25, rows[len(rows) // 2])
            seq += 1
            unit = _make_unit(
                catalog,
                def_id,
                side,
                placed,
                loadout_id=loadout_id if udef.category == "commander" else None,
                instance_id=f"{id_prefix}-{seq}-{def_id}",
                commander_avatar=commander_avatar if udef.category == "commander" else None,
            )
            if unit.is_multi_model:
                formation = deploy_formation(catalog, battle, unit, placed, occ)
                if formation is None:
                    # Fallback: stack temporarily then try wider — last resort keep anchor only
                    for m in unit.models:
                        m.position = placed
                    unit.sync_position_from_leader()
                    occ[hex_key(placed)] = unit.unit_instance_id
                else:
                    unit.place_models_at(formation)
            else:
                for m in unit.models:
                    m.position = placed
                unit.sync_position_from_leader()
                occ[hex_key(placed)] = unit.unit_instance_id
            battle.units[unit.unit_instance_id] = unit
            events.append(
                DomainEvent(
                    type="unit_deployed",
                    payload={
                        "unit_instance_id": unit.unit_instance_id,
                        "definition_id": def_id,
                        "side": side.value,
                        "position": unit.position.to_dict(),
                        "model_positions": [
                            {"model_id": m.model_id, "position": m.position.to_dict() if m.position else None}
                            for m in unit.models
                        ],
                    },
                )
            )
    return events


def _init_scenario(battle: BattleState, prep: dict) -> None:
    from .scenarios import OBJECTIVE_RADIUS, VP_TO_WIN, is_flag_scenario, scenario_meta, zone_layout

    scenario_id = prep.get("scenario_id") or "point_control"
    meta = scenario_meta(scenario_id)
    battle.scenario_id = scenario_id
    battle.objective_type = meta.get("objective_type", "zone_control")
    battle.scenario_meta = dict(meta)
    battle.objective_zones = zone_layout(scenario_id, battle.width, battle.height)
    battle.objective_radius = OBJECTIVE_RADIUS
    battle.vp_to_win = VP_TO_WIN
    if is_flag_scenario(scenario_id):
        battle.flags = [
            {
                "flag_id": z["id"],
                "label": z.get("label", z["id"]),
                "spawn_q": z["q"],
                "spawn_r": z["r"],
                "q": z["q"],
                "r": z["r"],
                "holder_unit_id": None,
                "side": None,
            }
            for z in battle.objective_zones
        ]


def create_battle(
    session_id: str,
    prep: dict,
    *,
    seed: int | None = None,
    battle_id: str | None = None,
) -> BattleState:
    from ..content.loader import load_catalog

    load_catalog(force=True)
    catalog = get_catalog()
    mission = catalog.missions[prep.get("mission_id", "freestyle_vs_15")]
    map_id = prep.get("map_id") or mission.map_id
    if map_id not in catalog.maps:
        raise ValueError(f"Unknown map_id '{map_id}'")
    map_def = catalog.maps[map_id]
    seed = seed if seed is not None else secrets.randbelow(2**31 - 2) + 1
    # Use provided seed directly
    rng = SeededRNG(seed)

    battle = BattleState(
        battle_id=battle_id or str(uuid4()),
        session_id=session_id,
        seed=seed,
        content_version=catalog.content_version,
        status=BattleStatus.INITIALIZING,
        mode=mission.mode,
        mission_id=mission.id,
        point_cap=int(prep.get("point_cap", mission.point_cap)),
        map_id=map_def.id,
        width=map_def.width,
        height=map_def.height,
        commander_avatar=prep.get("avatar", "male"),
        loadout_id=_commander_profile_id(catalog, prep),
        ram_abilities=list(prep.get("ram_abilities", []))[:3],
        opposition_ram_abilities=list(prep.get("opposition_ram_abilities", DEFAULT_OPPOSITION_RAM_ABILITIES))[:3],
    )
    for t in map_def.terrain:
        battle.terrain[f"{t['q']},{t['r']}"] = t["terrain_id"]

    # Friendly roster from prep
    army = prep.get("army", [])
    friendly_roster: list[tuple[str, int]] = []
    for entry in army:
        friendly_roster.append((entry["definition_id"], int(entry.get("count", 1))))
    # Always add commander
    friendly_roster = [("friendly_commander", 1)] + friendly_roster

    events: list[DomainEvent] = [
        DomainEvent(type="battle_deployed", payload={"seed": seed, "map_id": map_def.id, "point_cap": battle.point_cap})
    ]
    events.extend(
        _deploy_side(
            catalog,
            battle,
            friendly_roster,
            Side.FRIENDLY,
            map_def.friendly_deploy_rows,
            rng,
            loadout_id=battle.loadout_id,
            id_prefix="f",
            commander_avatar=battle.commander_avatar,
        )
    )

    opp_roster = build_opposition_force(
        catalog,
        battle.point_cap,
        rng,
        friendly_roster=[(d, c) for d, c in friendly_roster if d != "friendly_commander"],
    )
    opp_roster = [("opposition_commander", 1)] + list(opp_roster)
    events.extend(
        _deploy_side(
            catalog,
            battle,
            opp_roster,
            Side.OPPOSITION,
            map_def.opposition_deploy_rows,
            rng,
            loadout_id="red_commander",
            id_prefix="o",
        )
    )

    battle.status = BattleStatus.ACTIVE
    events.append(DomainEvent(type="battle_started", payload={"battle_id": battle.battle_id}))
    battle.commit_rng(rng)
    battle.append_events(events)
    _init_scenario(battle, prep)
    for u in battle.units.values():
        if u.definition_id == "friendly_commander_support_drone" and u.side == Side.FRIENDLY and u.alive:
            battle.support_drone_unit_id = u.unit_instance_id
            break
    start_round(battle)
    return battle


def start_round(battle: BattleState) -> list[dict]:
    catalog = get_catalog()
    battle.round += 1
    rng = battle.rng()
    events: list[DomainEvent] = []

    # Tick field effects (smoke fog duration)
    remaining_fx = []
    for fx in battle.field_effects:
        fx.rounds_remaining -= 1
        if fx.rounds_remaining > 0:
            remaining_fx.append(fx)
        else:
            events.append(
                DomainEvent(
                    type="field_effect_expired",
                    payload={"effect_id": fx.effect_id, "effect_type": fx.effect_type, "center": fx.center.to_dict()},
                )
            )
    battle.field_effects = remaining_fx

    # Tick statuses lightly — expire round-bound
    from .control_phase import clear_stale_allocated_ram

    clear_stale_allocated_ram(battle)
    for u in list(battle.units.values()):
        u.activated_this_round = False
        # End-of-round statuses
        u.statuses = [s for s in u.statuses if s not in ("targeting_assisted", "jammed", "revealed")]
        if "call_for_action" in u.statuses:
            u.speed = max(1, u.speed - 2)
            u.statuses = [s for s in u.statuses if s != "call_for_action"]
        # Spoof decoys expire at the start of each new round
        if u.category == "decoy" and u.alive:
            u.alive = False
            for m in u.models:
                m.alive = False
                m.hp = 0
            events.append(
                DomainEvent(
                    type="decoy_expired",
                    actor_id=u.unit_instance_id,
                    payload={"reason": "round_start"},
                )
            )

    cmd = battle.commander()
    opp_cmd = commander_for_side(battle, Side.OPPOSITION)
    for commander in (cmd, opp_cmd):
        if commander and commander.alive and commander.ram_capacity is not None:
            commander.ram_current = commander.ram_capacity
            events.append(
                DomainEvent(
                    type="resource_changed",
                    actor_id=commander.unit_instance_id,
                    payload={"resource": "ram", "remaining": commander.ram_current, "reason": "round_refresh"},
                )
            )

    # Initiative: friendly commander, opposition commander, then 1d20+Speed
    order: list[tuple[int, int, str]] = []
    others = [
        u
        for u in battle.living_units()
        if u.category not in ("commander", "decoy")
    ]
    for u in others:
        roll = rng.roll_d20()
        total = roll + u.speed
        order.append((total, u.speed, u.unit_instance_id))
        events.append(
            DomainEvent(
                type="initiative_rolled",
                actor_id=u.unit_instance_id,
                payload={"roll": roll, "speed": u.speed, "total": total},
            )
        )
    order.sort(key=lambda x: (x[0], x[1], x[2]), reverse=True)
    initiative = []
    if cmd and cmd.alive:
        initiative.append(cmd.unit_instance_id)
    if opp_cmd and opp_cmd.alive:
        initiative.append(opp_cmd.unit_instance_id)
    initiative.extend([uid for _, _, uid in order])
    battle.initiative = initiative
    battle.initiative_index = 0
    events.append(DomainEvent(type="round_started", payload={"round": battle.round, "initiative": initiative}))
    battle.commit_rng(rng)
    envelopes = battle.append_events(events)
    _begin_activation(battle)
    return envelopes


def _begin_activation(battle: BattleState) -> None:
    while battle.initiative_index < len(battle.initiative):
        uid = battle.initiative[battle.initiative_index]
        unit = battle.units.get(uid)
        if unit and unit.alive:
            # Support drone skips its own turn while the commander is aboard
            if unit.embarked_commander_id:
                battle.initiative_index += 1
                unit.activated_this_round = True
                continue
            # Defense Matrix lasts until the start of the next commander activation
            if unit.category == "commander" and "defense_matrix" in unit.statuses:
                unit.statuses = [s for s in unit.statuses if s != "defense_matrix"]
            # Painted lasts until the painter's next activation
            marker = f"painted_by:{uid}"
            for other in battle.units.values():
                if marker in other.statuses:
                    other.statuses = [s for s in other.statuses if s not in ("painted", marker)]

            from .control_phase import consume_allocated_ram_into_pool, start_control_phase

            bonus_std = 0
            if unit.category == "drone":
                bonus_std = consume_allocated_ram_into_pool(unit)
            battle.activation = ActivationState(
                activation_id=str(uuid4()),
                actor_id=uid,
                actions=ActionPool(standard=1 + bonus_std, move=1, minor=1),
            )
            catalog = get_catalog()
            from .resupply import try_resupply_at_deploy

            rearm_events = try_resupply_at_deploy(catalog, battle, unit)
            if rearm_events:
                battle.append_events(rearm_events)

            from .mines import check_unit_triggers_mines, refresh_detect_mines

            detect_events = refresh_detect_mines(catalog, battle)
            if detect_events:
                battle.append_events(detect_events)
            mine_events = check_unit_triggers_mines(catalog, battle, unit, reason="activation_start")
            if mine_events:
                battle.append_events(mine_events)
            if not unit.alive or battle.status != BattleStatus.ACTIVE:
                battle.initiative_index += 1
                unit.activated_this_round = True
                battle.activation = None
                _begin_activation(battle)
                return

            if unit.definition_id == "friendly_commander_support_drone" and "summoned_load" in unit.statuses:
                load_events = try_support_drone_auto_load(catalog, battle, unit)
                if load_events:
                    battle.append_events(load_events)
                if unit.embarked_commander_id:
                    battle.initiative_index += 1
                    unit.activated_this_round = True
                    battle.activation = None
                    _begin_activation(battle)
                    return

            if unit.category == "commander" and unit.ram_capacity is not None:
                cp_events = start_control_phase(battle, unit)
                if cp_events:
                    battle.append_events(cp_events)

            opts = build_options(catalog, battle, unit)
            battle.activation.options = opts
            battle.append_events(
                [
                    DomainEvent(
                        type="activation_started",
                        actor_id=uid,
                        payload={"activation_id": battle.activation.activation_id, "option_count": len(opts)},
                    )
                ]
            )
            return
        battle.initiative_index += 1
    # Round complete — score the temple, then deal the next round
    battle.activation = None
    if battle.status == BattleStatus.ACTIVE:
        from .objective import score_objective_at_round_end

        if battle.round >= 1:
            battle.append_events(score_objective_at_round_end(battle))
        if battle.status == BattleStatus.ACTIVE:
            start_round(battle)


def end_activation(battle: BattleState) -> list[dict]:
    if not battle.activation:
        return []
    uid = battle.activation.actor_id
    if uid in battle.units:
        battle.units[uid].activated_this_round = True
    events = [DomainEvent(type="activation_completed", actor_id=uid, payload={"activation_id": battle.activation.activation_id})]
    envelopes = battle.append_events(events)
    battle.initiative_index += 1
    battle.activation = None
    if battle.status == BattleStatus.ACTIVE:
        _begin_activation(battle)
    return envelopes


def _join_hex_path(first: list, second: list) -> list:
    if not first:
        return list(second or [])
    if not second:
        return list(first)
    a, b = first[-1], second[0]
    if isinstance(a, dict) and isinstance(b, dict) and a.get("q") == b.get("q") and a.get("r") == b.get("r"):
        return list(first) + list(second[1:])
    return list(first) + list(second)


def _join_model_paths(first: list, second: list) -> list:
    by_id: dict[str, dict] = {}
    for mp in first or []:
        mid = str(mp.get("model_id"))
        by_id[mid] = {"model_id": mid, "path": list(mp.get("path") or []), "to": mp.get("to")}
    for mp in second or []:
        mid = str(mp.get("model_id"))
        if mid in by_id:
            by_id[mid]["path"] = _join_hex_path(by_id[mid]["path"], mp.get("path") or [])
            by_id[mid]["to"] = mp.get("to") or by_id[mid]["to"]
        else:
            by_id[mid] = {"model_id": mid, "path": list(mp.get("path") or []), "to": mp.get("to")}
    return list(by_id.values())


def merge_chained_moves(events: list[dict], actor_id: str) -> None:
    """Fold extra unit_moved events into the first so the UI plays one path."""
    first: dict | None = None
    for env in events:
        if env.get("type") != "unit_moved" or env.get("actor_id") != actor_id:
            continue
        if first is None:
            first = env
            continue
        fp = first.setdefault("payload", {})
        ep = env.get("payload") or {}
        fp["path"] = _join_hex_path(fp.get("path") or [], ep.get("path") or [])
        fp["to"] = ep.get("to") or fp.get("to")
        fp["model_paths"] = _join_model_paths(fp.get("model_paths") or [], ep.get("model_paths") or [])
        anim = fp.setdefault("animation", {})
        anim["path"] = fp["path"]
        anim["model_paths"] = fp["model_paths"]
        anim["type"] = anim.get("type") or "move_path"
        env["type"] = "unit_moved_continued"


def execute_option(battle: BattleState, option_id: str) -> list[dict]:
    catalog = get_catalog()
    if battle.status != BattleStatus.ACTIVE:
        raise ValueError("Battle is not active")
    if not battle.activation:
        raise ValueError("No active activation")
    unit = battle.units[battle.activation.actor_id]
    opt = battle.activation.options.get(option_id)
    if not opt:
        # Snapshot rebuilds options with stable ids; persisted activation may still hold stale keys.
        battle.activation.options = build_options(catalog, battle, unit, sample_moves=0)
        opt = battle.activation.options.get(option_id)
    if not opt:
        raise ValueError("Unknown or expired option")
    if not unit.alive:
        raise ValueError("Actor defeated")

    events: list[DomainEvent] = []
    sub = opt["subroutine"]
    preview = opt.get("preview", {})

    if sub == "hold":
        events.append(DomainEvent(type="activation_skipped", actor_id=unit.unit_instance_id, payload={"reason": "hold"}))
        envelopes = battle.append_events(events)
        end_activation(battle)
        return envelopes

    if sub in ("move", "return_to_signal", "return_to_resupply"):
        dest = Hex(preview["affected_hexes"][0]["q"], preview["affected_hexes"][0]["r"])
        cost = int(preview.get("movement_cost") or 0)
        is_dash = bool(preview.get("dash")) or cost > unit.speed
        moves_needed = int(preview.get("moves_required") or 0) or (
            2 if is_dash else 1
        )
        # Prefer ceil(cost/speed) so RAM sprints (speed×3) burn three Move spends.
        from .options import moves_required_for_cost

        moves_needed = max(moves_needed, moves_required_for_cost(unit.speed, cost))
        budget = unit.speed * max(1, moves_needed)
        plans = plan_squad_move(catalog, battle, unit, dest, budget=budget)
        if not plans:
            raise ValueError("Illegal move")
        for i in range(moves_needed):
            if not battle.activation.actions.can_spend(ActionType.MOVE):
                if i == 0:
                    raise ValueError("No Move action remaining")
                break
            used = battle.activation.actions.spend(ActionType.MOVE)
            reason = "move" if i == 0 else ("sprint" if moves_needed >= 3 else "dash")
            events.append(
                DomainEvent(
                    type="action_spent",
                    actor_id=unit.unit_instance_id,
                    payload={"action": used.value, "for": reason},
                )
            )

        model_paths = []
        for plan in plans:
            model = next((m for m in unit.models if m.model_id == plan.model_id), None)
            if model and model.alive:
                model.position = plan.destination
            model_paths.append(
                {
                    "model_id": plan.model_id,
                    "path": [p.to_dict() for p in plan.path],
                    "to": plan.destination.to_dict(),
                }
            )
        unit.sync_position_from_leader()
        lead = unit.leader_model()
        leader_path = next(
            (p for p in plans if lead and p.model_id == lead.model_id),
            plans[0],
        )
        from .objective import sync_flag_positions

        sync_flag_positions(battle)
        events.append(
            DomainEvent(
                type="unit_moved",
                actor_id=unit.unit_instance_id,
                payload={
                    "path": [p.to_dict() for p in leader_path.path],
                    "to": unit.position.to_dict(),
                    "model_paths": model_paths,
                    "animation": {
                        "type": "squad_move" if unit.is_multi_model else "move_path",
                        "path": [p.to_dict() for p in leader_path.path],
                        "model_paths": model_paths,
                    },
                },
            )
        )
        from .mines import check_unit_triggers_mines, refresh_detect_mines
        from .resupply import try_resupply_at_deploy

        events.extend(try_resupply_at_deploy(catalog, battle, unit))
        events.extend(refresh_detect_mines(catalog, battle))
        events.extend(check_unit_triggers_mines(catalog, battle, unit, reason="entered_hex"))
        envelopes = battle.append_events(events)
        if battle.status != BattleStatus.ACTIVE or not unit.alive:
            if battle.activation and unit.alive is False:
                end_activation(battle)
            return envelopes
        battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    if sub == "attack":
        from .options import _any_shooter_can_hit_unit

        if not battle.activation.actions.can_spend(ActionType.STANDARD):
            raise ValueError("No attack remaining (already double-moved or spent Standard)")
        weapon_id = preview.get("weapon_id")
        target_id = preview.get("target_unit_id")
        target_model_id = preview.get("target_model_id")
        if not weapon_id or not target_id or target_id not in battle.units:
            raise ValueError("Unknown or expired attack option")
        target = battle.units[target_id]
        weapon = catalog.weapons.get(weapon_id)
        if not weapon:
            raise ValueError("Unknown weapon")
        if not target.alive:
            raise ValueError("Target is already down")
        if not _any_shooter_can_hit_unit(catalog, battle, unit, target, weapon.range):
            raise ValueError("Target out of range or no line of sight")
        events = resolve_attack(catalog, battle, unit, weapon_id, target, target_model_id=target_model_id)
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE and battle.activation:
            battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    if sub == "grab_flag":
        if not battle.activation.actions.can_spend(ActionType.STANDARD):
            raise ValueError("No Standard action remaining")
        flag_id = preview.get("flag_id")
        if not flag_id:
            raise ValueError("Unknown flag")
        used = battle.activation.actions.spend(ActionType.STANDARD)
        events.append(
            DomainEvent(type="action_spent", actor_id=unit.unit_instance_id, payload={"action": used.value, "for": "grab_flag"})
        )
        from .objective import resolve_grab_flag

        events.extend(resolve_grab_flag(battle, unit, flag_id))
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE and battle.activation:
            battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    if sub == "self_destruct":
        if "jammed" in unit.statuses:
            raise ValueError("Jammed units cannot use special abilities")
        events = resolve_self_destruct(catalog, battle, unit)
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE:
            end_activation(battle)
        return envelopes

    if sub == "paint_target":
        target_id = preview["target_unit_id"]
        target = battle.units[target_id]
        events = resolve_paint_target(catalog, battle, unit, target)
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE and battle.activation:
            battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    if sub == "drop_smoke":
        events = resolve_drop_smoke(catalog, battle, unit)
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE and battle.activation:
            battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    if sub == "deploy_mine":
        from .mines import resolve_deploy_mine

        dest = Hex(preview["affected_hexes"][0]["q"], preview["affected_hexes"][0]["r"])
        events = resolve_deploy_mine(catalog, battle, unit, dest)
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE and battle.activation:
            battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    if sub == "ram_ability":
        ability_id = preview["ability_id"]
        fresh = build_options(catalog, battle, unit, sample_moves=0).get(option_id)
        if not fresh or fresh.get("subroutine") != "ram_ability":
            raise ValueError("Unknown or expired RAM ability")
        fresh_preview = fresh.get("preview") or {}
        if fresh_preview.get("disabled") or fresh_preview.get("blocked_reason"):
            raise ValueError(fresh_preview.get("blocked_reason") or "Ability is not available")
        if fresh_preview.get("needs_target"):
            raise ValueError("This RAM ability needs a target — pick unit/hex in the RAM panel")
        target_unit_id = fresh_preview.get("target_unit_id")
        target_hex = None
        events = resolve_ram_ability(catalog, battle, unit, ability_id, target_hex, target_unit_id)
        envelopes = battle.append_events(events)
        if battle.status == BattleStatus.ACTIVE and battle.activation:
            battle.activation.options = build_options(catalog, battle, unit)
        return envelopes

    raise ValueError(f"Unsupported subroutine {sub}")


def validate_army(prep: dict) -> list[str]:
    catalog = get_catalog()
    errors: list[str] = []
    point_cap = int(prep.get("point_cap", 15))
    army = prep.get("army", [])
    total = 0
    unit_count = 0
    counts: dict[str, int] = {}
    for entry in army:
        def_id = entry["definition_id"]
        count = int(entry.get("count", 1))
        if def_id not in catalog.units:
            errors.append(f"Unknown unit {def_id}")
            continue
        udef = catalog.units[def_id]
        if "friendly" not in udef.side_availability:
            errors.append(f"{def_id} is not friendly-buildable")
        if udef.category == "commander":
            errors.append("Do not include commander in army list")
        total += udef.point_cost * count
        unit_count += count
        counts[def_id] = counts.get(def_id, 0) + count
        if udef.max_per_army is not None and counts[def_id] > udef.max_per_army:
            errors.append(f"{def_id} exceeds max_per_army")
    if total > point_cap:
        errors.append(f"Army costs {total} > cap {point_cap}")
    if unit_count > 10:
        errors.append("Max 10 non-commander units")
    profile_id = _commander_profile_id(catalog, prep)
    if profile_id not in catalog.loadouts:
        errors.append("Invalid commander avatar")
    else:
        allowed = set(catalog.loadouts[profile_id].allowed_abilities)
        abilities = prep.get("ram_abilities", [])
        if len(abilities) != 3:
            errors.append("Select exactly 3 RAM abilities")
        for a in abilities:
            if a not in allowed:
                errors.append(f"Ability {a} not allowed for commander")
    avatar = prep.get("avatar")
    if not avatar:
        errors.append("Avatar required")
    elif avatar not in catalog.loadouts:
        errors.append("Invalid avatar")
    return errors
