"""Tactical option generation for player and agents."""

from __future__ import annotations

from uuid import uuid4

from ..content.loader import ContentCatalog
from ..domain.enums import ActionType, Side
from ..domain.hex import Hex, axial_distance, hex_key, hexes_in_radius, parse_hex
from .formation import plan_squad_move, squad_can_engage_target
from .objective import hex_in_objective, objective_hex, unit_contests_objective
from .pathfinding import find_path, reachable_hexes
from .resupply import (
    deploy_anchor,
    hex_in_deploy,
    should_return_to_resupply,
)
from .field_effects import find_support_drone
from .state import BattleState, UnitState, combat_profile, has_line_of_sight, in_signal, is_targetable, unit_within_radius


def stable_option_id(subroutine: str, preview: dict | None = None) -> str:
    """Deterministic option keys so rebuilds after move/RAM still match the UI."""
    preview = preview or {}
    if subroutine == "hold":
        return "hold"
    if subroutine == "self_destruct":
        return "self_destruct"
    if subroutine == "attack":
        return f"attack:{preview.get('weapon_id')}:{preview.get('target_unit_id')}"
    if subroutine == "paint_target":
        return f"paint:{preview.get('target_unit_id')}"
    if subroutine == "drop_smoke":
        return "drop_smoke"
    if subroutine == "deploy_mine":
        hexes = preview.get("affected_hexes") or []
        if hexes:
            return f"deploy_mine:{hexes[0].get('q')}:{hexes[0].get('r')}"
        return "deploy_mine"
    if subroutine == "grab_flag":
        return f"grab_flag:{preview.get('flag_id')}"
    if subroutine == "ram_ability":
        return f"ram:{preview.get('ability_id')}"
    if subroutine in ("move", "return_to_signal", "return_to_resupply"):
        hexes = preview.get("affected_hexes") or []
        if hexes:
            return f"{subroutine}:{hexes[0].get('q')}:{hexes[0].get('r')}"
        dest = preview.get("path") or []
        if dest:
            last = dest[-1]
            return f"{subroutine}:{last.get('q')}:{last.get('r')}"
    return f"{subroutine}:{uuid4()}"


def remaining_move_spends(actions) -> int:
    """How many Move spends are left (Move pool + each Standard usable as Move)."""
    return int(getattr(actions, "move", 0) or 0) + int(getattr(actions, "standard", 0) or 0)


def moves_required_for_cost(speed: int, cost: int) -> int:
    """How many Move spends a path of `cost` burns (ceil(cost/speed), min 1)."""
    spd = max(1, int(speed or 1))
    if cost <= 0:
        return 1
    return max(1, (int(cost) + spd - 1) // spd)


def agent_move_budget(catalog: ContentCatalog, battle: BattleState, unit: UnitState) -> int:
    """Path budget for this activation. Bombers / RTB may burn every remaining Move spend in one path."""
    speed = max(1, int(unit.speed or 1))
    if not battle.activation:
        return speed
    spends = remaining_move_spends(battle.activation.actions)
    if spends < 2:
        return speed
    if should_return_to_resupply(catalog, unit):
        return speed * min(2, spends)
    # One-way bombers: Self-destruct is Minor — spend every Move (incl. RAM Standards) closing in.
    if _is_disposable_bomber(unit):
        return speed * spends
    return speed


def should_chain_dash(
    catalog: ContentCatalog, battle: BattleState, unit: UnitState, last_subroutine: str
) -> bool:
    """True when the leftover action should be another move, not a shot."""
    if last_subroutine not in ("move", "return_to_signal", "return_to_resupply"):
        return False
    if not battle.activation or battle.activation.actor_id != unit.unit_instance_id:
        return False
    actions = battle.activation.actions
    if not actions.can_spend(ActionType.MOVE):
        return False
    # Non-bombers: classic double-move cap (don't burn RAM Standards as a third Move when guns exist).
    if not _is_disposable_bomber(unit) and actions.moves_spent >= 2:
        return False
    remaining = battle.activation.options or {}
    has_attack = actions.can_spend(ActionType.STANDARD) and any(
        o.get("subroutine") == "attack" for o in remaining.values()
    )
    # Self-destruct is a Minor kill — never dash past a legal detonation
    has_suicide = actions.can_spend(ActionType.MINOR) and any(
        o.get("subroutine") == "self_destruct" for o in remaining.values()
    )
    if has_suicide:
        return False
    has_move = any(
        o.get("subroutine") in ("move", "return_to_signal", "return_to_resupply") for o in remaining.values()
    )
    if not has_move:
        return False
    # Bombers: burn every Move spend (RAM = triple Move) then Minor detonate.
    if _is_disposable_bomber(unit):
        return True
    from .resupply import must_return_to_resupply

    combat_dry = must_return_to_resupply(catalog, unit)
    # Prefer shooting over a second move when a real attack is still legal
    # (empty missiles + working rifle still counts as has_attack).
    if has_attack:
        return False
    already_contesting = unit_contests_objective(battle, unit)
    return combat_dry or not already_contesting


def _plans_enter_objective(battle: BattleState, dest: Hex, plans: list | None) -> bool:
    if plans:
        return any(hex_in_objective(battle, p.destination) for p in plans)
    return hex_in_objective(battle, dest)


def _closes_on_objective(battle: BattleState, from_hex: Hex, to_hex: Hex) -> bool:
    obj = objective_hex(battle)
    return axial_distance(to_hex, obj) < axial_distance(from_hex, obj)


def _is_striker(unit: UnitState) -> bool:
    """Flying/strike drones hunt; they are not temple cappers."""
    if unit.category == "drone":
        return True
    return bool({"mobile_damage", "area_damage", "disposable"} & set(unit.roles)) and "frontline" not in unit.roles


def _is_disposable_bomber(unit: UnitState) -> bool:
    """One-way / impact drones exist to detonate on clustered foes — not to cap the temple."""
    return "disposable" in unit.roles and any(a.startswith("self_destruct") for a in (unit.abilities or []))


def _closes_on_enemy(from_hex: Hex, to_hex: Hex, enemies: list[UnitState]) -> bool:
    if not enemies:
        return False
    before = min(axial_distance(from_hex, e.position) for e in enemies)
    after = min(axial_distance(to_hex, e.position) for e in enemies)
    return after < before


def _move_detonation_preview(
    catalog: ContentCatalog, battle: BattleState, unit: UnitState, dest: Hex
) -> dict:
    blast = self_destruct_blast_assessment(catalog, battle, unit, at_hex=dest)
    enemy_models = int(blast.get("enemy_models_in_blast") or 0)
    friendly_models = int(blast.get("friendly_models_in_blast") or 0)
    foes = battle.living_units(Side.OPPOSITION if unit.side == Side.FRIENDLY else Side.FRIENDLY)
    return {
        "detonation_would_hit": enemy_models > 0,
        "detonation_enemy_models": enemy_models,
        "detonation_friendly_models": friendly_models,
        "closes_on_enemy": _closes_on_enemy(unit.position, dest, foes),
    }


def _attack_target_in_objective(battle: BattleState | None, opt: dict) -> bool:
    if not battle:
        return False
    tid = (opt.get("preview") or {}).get("target_unit_id")
    if not tid:
        return False
    target = battle.units.get(tid)
    return bool(target and unit_contests_objective(battle, target))


def list_reachable(catalog: ContentCatalog, battle: BattleState, unit: UnitState) -> list[dict]:
    """Full reachable hex list for player map UI (excludes current cell)."""
    if not battle.activation or battle.activation.actor_id != unit.unit_instance_id:
        return []
    if not battle.activation.actions.can_spend(ActionType.MOVE):
        return []
    reach = reachable_hexes(catalog, battle, unit)
    out: list[dict] = []
    for key, cost in reach.items():
        if cost == 0:
            continue
        q, r = map(int, key.split(","))
        dest = Hex(q, r)
        if unit.is_multi_model and plan_squad_move(catalog, battle, unit, dest) is None:
            continue
        out.append({"q": q, "r": r, "cost": cost})
    out.sort(key=lambda h: (h["cost"], h["q"], h["r"]))
    return out


def make_move_option(catalog: ContentCatalog, battle: BattleState, unit: UnitState, q: int, r: int) -> dict:
    """Build a single validated move option for a destination hex."""
    if not battle.activation or battle.activation.actor_id != unit.unit_instance_id:
        raise ValueError("Not this unit's activation")
    if not battle.activation.actions.can_spend(ActionType.MOVE):
        raise ValueError("No Move action remaining")
    dest = Hex(q, r)
    reach = reachable_hexes(catalog, battle, unit)
    key = f"{q},{r}"
    if key not in reach or reach[key] == 0:
        raise ValueError("Destination not reachable")
    plans = plan_squad_move(catalog, battle, unit, dest)
    if not plans:
        raise ValueError("Illegal move")
    cost = reach[key]
    oid = stable_option_id("move", {"affected_hexes": [dest.to_dict()]})
    leader_path = plans[0].path
    lead = unit.leader_model()
    if lead:
        leader_path = next((p.path for p in plans if p.model_id == lead.model_id), plans[0].path)
    model_paths = [
        {"model_id": p.model_id, "path": [h.to_dict() for h in p.path], "to": p.destination.to_dict()} for p in plans
    ]
    return {
        "option_id": oid,
        "activation_id": battle.activation.activation_id,
        "actor_id": unit.unit_instance_id,
        "subroutine": "move",
        "label": f"Move to ({dest.q},{dest.r})",
        "action_cost": "move",
        "target_refs": [{"type": "hex", "q": dest.q, "r": dest.r}],
        "preview": {
            "path": [p.to_dict() for p in leader_path],
            "model_paths": model_paths,
            "movement_cost": cost,
            "affected_hexes": [dest.to_dict()],
            "risk_tags": [],
            "enters_objective": _plans_enter_objective(battle, dest, plans),
            "closes_on_objective": _closes_on_objective(battle, unit.position, dest),
            "center_dist": axial_distance(dest, objective_hex(battle)),
            "enters_resupply": hex_in_deploy(battle, unit.side, dest),
            "closes_on_resupply": axial_distance(dest, deploy_anchor(battle, unit.side))
            < axial_distance(unit.position, deploy_anchor(battle, unit.side)),
            **(
                _move_detonation_preview(catalog, battle, unit, dest)
                if _is_disposable_bomber(unit)
                else {}
            ),
        },
        "issued_state_version": battle.state_version,
        "expires_with_activation": True,
    }


def _model_can_shoot(
    catalog: ContentCatalog,
    battle: BattleState,
    attacker: UnitState,
    from_hex: Hex,
    to_hex: Hex,
    weapon_range: int,
) -> bool:
    from .formation import model_can_shoot

    return model_can_shoot(catalog, battle, from_hex, to_hex, weapon_range)


def _self_destruct_area(catalog: ContentCatalog, unit: UnitState) -> int:
    ability = None
    for aid in unit.abilities:
        if aid.startswith("self_destruct"):
            ability = catalog.abilities.get(aid)
            break
    if ability is None:
        ability = catalog.abilities.get("self_destruct")
    return int(getattr(ability, "area", 1) or 1) if ability else 1


def self_destruct_blast_assessment(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    *,
    at_hex: Hex | None = None,
) -> dict:
    """List living enemy/friendly models that would be clipped by detonating at at_hex (default: current)."""
    area = _self_destruct_area(catalog, unit)
    center = at_hex or unit.position
    blast = {hex_key(h) for h in hexes_in_radius(center, area, battle.width, battle.height)}
    enemies_in_blast: list[dict] = []
    friendlies_in_blast: list[dict] = []
    for other in battle.units.values():
        if not other.alive or other.category == "decoy":
            continue
        if other.unit_instance_id == unit.unit_instance_id:
            # Detonating unit always dies; track separately from collateral friendlies
            continue
        models_hit: list[str] = []
        victims = list(other.living_models) or ([None] if other.alive else [])
        for model in victims:
            pos = other.model_position(model) if model is not None else other.position
            if hex_key(pos) in blast:
                models_hit.append(model.model_id if model is not None else "unit")
        if not models_hit:
            continue
        entry = {
            "unit_instance_id": other.unit_instance_id,
            "name": other.display_name,
            "definition_id": other.definition_id,
            "models_in_blast": len(models_hit),
            "is_commander": other.category == "commander",
        }
        if other.side == unit.side:
            friendlies_in_blast.append(entry)
        else:
            enemies_in_blast.append(entry)
    return {
        "blast_radius": area,
        "impact": center.to_dict(),
        "enemies_in_blast": enemies_in_blast,
        "friendlies_in_blast": friendlies_in_blast,
        "enemy_models_in_blast": sum(e["models_in_blast"] for e in enemies_in_blast),
        "friendly_models_in_blast": sum(f["models_in_blast"] for f in friendlies_in_blast),
        "friendly_fire": bool(friendlies_in_blast),
    }


def self_destruct_hits_enemy(catalog: ContentCatalog, battle: BattleState, unit: UnitState) -> bool:
    """True if detonating at the unit's hex would clip a living enemy model."""
    return bool(self_destruct_blast_assessment(catalog, battle, unit)["enemies_in_blast"])


def _any_shooter_can_hit_unit(
    catalog: ContentCatalog,
    battle: BattleState,
    attacker: UnitState,
    target: UnitState,
    weapon_range: int,
) -> bool:
    """True if the attacker can engage any living model of the target unit (now or after aiming)."""
    if target.category == "decoy":
        return _model_can_shoot(
            catalog, battle, attacker, attacker.position, target.position, weapon_range
        )
    if attacker.category == "soldier_squad" or attacker.is_multi_model:
        return squad_can_engage_target(catalog, battle, attacker, target, weapon_range)
    shooters = attacker.living_models[:1] or attacker.models[:1]
    for sm in shooters:
        from_hex = attacker.model_position(sm)
        for em in target.living_models:
            if _model_can_shoot(catalog, battle, attacker, from_hex, target.model_position(em), weapon_range):
                return True
    return False



def build_options(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    limit: int = 12,
    sample_moves: int = 5,
) -> dict[str, dict]:
    """Return option_id -> option dict. Always includes hold. Agents get sampled moves."""
    from .mines import refresh_detect_mines

    # Passive Detect Mine aura keeps hostile mines revealed for everyone who can see them.
    detect_events = refresh_detect_mines(catalog, battle)
    if detect_events:
        battle.append_events(detect_events)

    options: dict[str, dict] = {}
    if not battle.activation or battle.activation.actor_id != unit.unit_instance_id:
        return options
    actions = battle.activation.actions
    issued = battle.state_version

    def add(
        subroutine: str,
        label: str,
        action_cost: str,
        target_refs: list,
        preview: dict,
        risk_tags: list | None = None,
        *,
        force: bool = False,
    ):
        if not force and len(options) >= limit:
            return
        oid = stable_option_id(subroutine, preview)
        if oid in options:
            oid = f"{oid}:{len(options)}"
        options[oid] = {
            "option_id": oid,
            "activation_id": battle.activation.activation_id,
            "actor_id": unit.unit_instance_id,
            "subroutine": subroutine,
            "label": label,
            "action_cost": action_cost,
            "target_refs": target_refs,
            "preview": {**preview, "risk_tags": risk_tags or []},
            "issued_state_version": issued,
            "expires_with_activation": True,
        }

    # Hold always
    add("hold", "Hold position", "none", [], {"path": [], "movement_cost": 0, "affected_hexes": []})

    # Move options — sample destinations for agent menus (player uses full reachable + move_to)
    move_budget = agent_move_budget(catalog, battle, unit)
    sample_n = sample_moves
    if _is_disposable_bomber(unit):
        # More candidates so blast hexes survive sampling on long dashes
        sample_n = max(sample_moves, 8)
    if actions.can_spend(ActionType.MOVE) and sample_n > 0:
        reach = reachable_hexes(catalog, battle, unit, budget=move_budget)
        # Prefer forward toward map center / enemy / objective
        scored: list[tuple[int, Hex, int]] = []
        enemies = battle.living_units(Side.OPPOSITION if unit.side == Side.FRIENDLY else Side.FRIENDLY)
        objective = objective_hex(battle)
        already_in_zone = hex_in_objective(battle, unit.position)
        rearming = should_return_to_resupply(catalog, unit)
        home = deploy_anchor(battle, unit.side)
        order_tags: set[str] = set()
        if unit.side == Side.FRIENDLY:
            for d in battle.directives or []:
                if not d.get("active"):
                    continue
                if d.get("scope") == "global" or d.get("target_unit_id") == unit.unit_instance_id:
                    order_tags.update(d.get("derived_tags") or [])
        push_orders = bool(order_tags & {"advance", "objective", "center", "engage", "attack", "focus_fire", "screen", "commander_protective"})
        hold_orders = bool(order_tags & {"hold", "defensive"}) and not push_orders
        disposable_bomber = _is_disposable_bomber(unit)
        for key, cost in reach.items():
            if cost == 0:
                continue
            q, r = map(int, key.split(","))
            h = Hex(q, r)
            enemy_dist = min((axial_distance(h, e.position) for e in enemies), default=50)
            center_dist = axial_distance(h, objective)
            in_zone = hex_in_objective(battle, h)
            # Default assault: contest the temple and close on enemies
            score = -enemy_dist * 8 - center_dist * 12 - cost
            if disposable_bomber:
                det = self_destruct_blast_assessment(catalog, battle, unit, at_hex=h)
                enemy_models = int(det.get("enemy_models_in_blast") or 0)
                friendly_models = int(det.get("friendly_models_in_blast") or 0)
                if enemy_models > 0:
                    # Must outrank any troop_pull hunt score (those can hit thousands).
                    score = 100_000 + enemy_models * 90 - friendly_models * 50 - cost
                else:
                    # Close on nearest enemy this activation — do not chase distant infantry
                    # past a closer dog/drone that is still out of blast.
                    score = -enemy_dist * 40 - cost
                    for e in enemies:
                        ed = axial_distance(h, e.position)
                        # Soft bonus for multi-model packs only when equally close
                        if e.category == "soldier_squad":
                            score += max(0, 8 - ed) * len(e.living_models)
                    if push_orders:
                        score -= center_dist * 2
            elif "support" in unit.roles and "frontline" not in unit.roles:
                if unit.side == Side.FRIENDLY and not push_orders:
                    # Friendly support hangs back unless army orders say push
                    score = enemy_dist * 2 - center_dist - cost
                    if hold_orders:
                        score = enemy_dist * 3 - cost
                else:
                    # Opposition support, or friendly support under push orders
                    score = -center_dist * 14 - enemy_dist * 4 - cost
            if push_orders and not disposable_bomber:
                score = -center_dist * 12 - enemy_dist * 8 - cost
            if in_zone and not disposable_bomber:
                score += 55
            if not already_in_zone and in_zone and not disposable_bomber:
                score += 40
            if rearming:
                home_dist = axial_distance(h, home)
                score = -home_dist * 20 - cost
                if hex_in_deploy(battle, unit.side, h):
                    score += 100
            scored.append((score, h, cost))
        scored.sort(key=lambda x: x[0], reverse=True)
        ordered = scored
        blast_hexes: list[tuple[int, Hex, int]] = []
        if scored:
            if disposable_bomber:
                blast_hexes = [s for s in scored if s[0] >= 100_000]
                if blast_hexes:
                    # Only land where the blast clips an enemy this activation.
                    ordered = blast_hexes
                else:
                    # Nearest living foe (dogs/drones count equal to infantry)
                    goal = home if rearming else (
                        min(
                            enemies,
                            key=lambda e: (
                                axial_distance(unit.position, e.position),
                                -len(e.living_models),
                                e.unit_instance_id,
                            ),
                        ).position
                        if enemies
                        else objective
                    )
                    closest = min(scored, key=lambda x: (axial_distance(x[1], goal), -x[0], x[1].q, x[1].r))
                    ordered = [closest] + [item for item in scored if item[1] != closest[1]]
            else:
                goal = home if rearming else objective
                closest = min(scored, key=lambda x: (axial_distance(x[1], goal), -x[0], x[1].q, x[1].r))
                ordered = [closest] + [item for item in scored if item[1] != closest[1]]

        def _add_bomber_move(dest: Hex, cost: int) -> bool:
            plans = plan_squad_move(catalog, battle, unit, dest, budget=move_budget)
            if not plans:
                return False
            lead = unit.leader_model()
            leader_path = next((p.path for p in plans if lead and p.model_id == lead.model_id), plans[0].path)
            model_paths = [
                {"model_id": p.model_id, "path": [h.to_dict() for h in p.path], "to": p.destination.to_dict()}
                for p in plans
            ]
            is_dash = cost > unit.speed
            moves_burned = moves_required_for_cost(unit.speed, cost)
            if moves_burned >= 3:
                move_label = f"Sprint to ({dest.q},{dest.r})"
            elif is_dash:
                move_label = f"Dash to ({dest.q},{dest.r})"
            else:
                move_label = f"Move to ({dest.q},{dest.r})"
            add(
                "move",
                move_label,
                "move",
                [{"type": "hex", "q": dest.q, "r": dest.r}],
                {
                    "path": [p.to_dict() for p in leader_path],
                    "model_paths": model_paths,
                    "movement_cost": cost,
                    "dash": is_dash,
                    "moves_required": moves_burned,
                    "affected_hexes": [dest.to_dict()],
                    "enters_objective": _plans_enter_objective(battle, dest, plans),
                    "closes_on_objective": _closes_on_objective(battle, unit.position, dest),
                    "center_dist": axial_distance(dest, objective),
                    "enters_resupply": hex_in_deploy(battle, unit.side, dest),
                    "closes_on_resupply": axial_distance(dest, home) < axial_distance(unit.position, home),
                    **(
                        _move_detonation_preview(catalog, battle, unit, dest)
                        if disposable_bomber
                        else {}
                    ),
                },
            )
            return True

        # Bombers: force every reachable blast hex into the menu before sample limits.
        if disposable_bomber and blast_hexes:
            for _, dest, cost in blast_hexes:
                _add_bomber_move(dest, cost)
        else:
            for _, dest, cost in ordered[: sample_n * 3]:
                if not _add_bomber_move(dest, cost):
                    continue
                move_count = sum(1 for o in options.values() if o["subroutine"] == "move")
                if move_count >= sample_n:
                    break

    actor = combat_profile(battle, unit)

    # Attack options — one engagement per enemy unit (volley retargets models as they drop)
    if actions.can_spend(ActionType.STANDARD):
        enemies = battle.living_units(Side.OPPOSITION if unit.side == Side.FRIENDLY else Side.FRIENDLY)
        targets: list[UnitState] = []
        for e in enemies:
            if e.category == "decoy" and unit.side == Side.FRIENDLY:
                continue
            if not is_targetable(e):
                continue
            targets.append(e)
        targets.sort(
            key=lambda e: (
                0 if e.category == "commander" else 1,
                axial_distance(unit.position, e.position),
                e.unit_instance_id,
            )
        )
        for weapon_id in actor.weapons:
            weapon = catalog.weapons.get(weapon_id)
            if not weapon:
                continue
            if weapon.ammo is not None and unit.ammo.get(weapon_id, weapon.ammo) <= 0:
                continue
            for enemy in targets:
                if not _any_shooter_can_hit_unit(catalog, battle, unit, enemy, weapon.range):
                    continue
                # Preferred opening model: nearest living model from unit leader
                emodel = enemy.leader_model() or next(iter(enemy.living_models), None)
                if enemy.living_models:
                    emodel = min(
                        enemy.living_models,
                        key=lambda m: (axial_distance(unit.position, enemy.model_position(m)), m.model_id),
                    )
                epos = enemy.model_position(emodel) if emodel else enemy.position
                label = f"Fire {weapon.display_name} at {enemy.display_name}"
                add(
                    "attack",
                    label,
                    "standard",
                    [
                        {"type": "unit", "unit_instance_id": enemy.unit_instance_id},
                        *([{"type": "model", "model_id": emodel.model_id}] if emodel else []),
                        {"type": "weapon", "weapon_id": weapon_id},
                    ],
                    {
                        "path": [],
                        "movement_cost": 0,
                        "affected_hexes": [epos.to_dict()],
                        "weapon_id": weapon_id,
                        "target_unit_id": enemy.unit_instance_id,
                        "target_model_id": emodel.model_id if emodel else None,
                    },
                    risk_tags=["friendly_fire"] if weapon.area else [],
                )
                if len(options) >= limit:
                    break
            if len(options) >= limit:
                break

        from .objective import grab_flag_options

        for flag in grab_flag_options(battle, unit):
            label = f"Grab {flag.get('label', flag['flag_id'])} flag"
            add(
                "grab_flag",
                label,
                "standard",
                [{"type": "flag", "flag_id": flag["flag_id"]}],
                {
                    "path": [],
                    "movement_cost": 0,
                    "affected_hexes": [{"q": flag["q"], "r": flag["r"]}],
                    "flag_id": flag["flag_id"],
                },
            )

    # Self-destruct is Minor — must still be legal AFTER a dash (moves_spent==2 kills Standard/Attack).
    # Previously this lived inside can_spend(STANDARD), so bombers parked on blast hexes and never detonated.
    if (
        actions.can_spend(ActionType.MINOR)
        and any(a.startswith("self_destruct") for a in unit.abilities)
        and "jammed" not in unit.statuses
        and self_destruct_hits_enemy(catalog, battle, unit)
    ):
        blast = self_destruct_blast_assessment(catalog, battle, unit)
        risks = ["suicide", "aoe"]
        if blast.get("friendly_fire"):
            risks.append("friendly_fire")
        add(
            "self_destruct",
            "Self-destruct",
            "minor",
            [{"type": "hex", **unit.position.to_dict()}],
            {
                "path": [],
                "movement_cost": 0,
                "affected_hexes": [unit.position.to_dict()],
                "blast_radius": blast["blast_radius"],
                "enemies_in_blast": blast["enemies_in_blast"],
                "friendlies_in_blast": blast["friendlies_in_blast"],
                "enemy_models_in_blast": blast["enemy_models_in_blast"],
                "friendly_models_in_blast": blast["friendly_models_in_blast"],
                "friendly_fire": blast["friendly_fire"],
            },
            risk_tags=risks,
        )

    if "drop_smoke" in unit.abilities and actions.can_spend(ActionType.MINOR):
        smoke = catalog.abilities.get("drop_smoke")
        radius = int(getattr(smoke, "area", 2) or 2) if smoke else 2
        center = unit.position
        affected = [h.to_dict() for h in hexes_in_radius(center, radius, battle.width, battle.height)]
        add(
            "drop_smoke",
            "Drop Smoke",
            "minor",
            [{"type": "hex", **center.to_dict()}],
            {"path": [], "movement_cost": 0, "affected_hexes": affected},
        )

    if "deploy_mine" in unit.abilities and actions.can_attack():
        from .mines import adjacent_deploy_hexes

        occ = battle.occupancy()
        obj = objective_hex(battle)
        foes = [
            u
            for u in battle.living_units(Side.OPPOSITION if unit.side == Side.FRIENDLY else Side.FRIENDLY)
            if u.category != "decoy"
        ]
        for h in adjacent_deploy_hexes(battle, unit):
            occ_id = occ.get(f"{h.q},{h.r}")
            on_enemy = False
            if occ_id:
                other = battle.units.get(occ_id)
                on_enemy = bool(other and other.alive and other.side != unit.side and other.category != "decoy")
            center_dist = axial_distance(h, obj)
            near_objective = hex_in_objective(battle, h) or center_dist <= 8
            # Preemptive corridor: hex is closer to a foe than we are (they'll walk through it).
            on_approach = False
            if foes and not on_enemy:
                for foe in foes:
                    if axial_distance(h, foe.position) < axial_distance(unit.position, foe.position):
                        on_approach = True
                        break
            add(
                "deploy_mine",
                f"Deploy Mine ({h.q},{h.r})" + (" under enemy" if on_enemy else ""),
                "standard",
                [{"type": "hex", "q": h.q, "r": h.r}],
                {
                    "path": [],
                    "movement_cost": 0,
                    "affected_hexes": [{"q": h.q, "r": h.r}],
                    "under_enemy": on_enemy,
                    "in_own_deploy": hex_in_deploy(battle, unit.side, h),
                    "near_objective": near_objective,
                    "on_approach": on_approach,
                    "center_dist": center_dist,
                    "risk_tags": ["friendly_fire"] if on_enemy else [],
                },
                risk_tags=["friendly_fire"] if on_enemy else None,
                force=True,
            )

    # Paint Target (soldier minor — enables Airstrike)
    if "paint_target" in unit.abilities and actions.can_spend(ActionType.MINOR):
        paint_ability = catalog.abilities.get("paint_target")
        paint_range = paint_ability.range if paint_ability and paint_ability.range else 12
        enemies = [
            u
            for u in battle.living_units(Side.OPPOSITION if unit.side == Side.FRIENDLY else Side.FRIENDLY)
            if u.category != "decoy"
        ]
        for enemy in enemies:
            dist = axial_distance(unit.position, enemy.position)
            if dist > paint_range:
                continue
            if not has_line_of_sight(catalog, battle, unit.position, enemy.position):
                continue
            add(
                "paint_target",
                f"Paint {enemy.display_name}",
                "minor",
                [{"type": "unit", "unit_instance_id": enemy.unit_instance_id}],
                {
                    "path": [],
                    "movement_cost": 0,
                    "affected_hexes": [enemy.position.to_dict()],
                    "target_unit_id": enemy.unit_instance_id,
                },
            )
            if len(options) >= limit:
                break

    # Empty Blue Direct Attack Drone flies home to the deployment belt to rearm
    if should_return_to_resupply(catalog, unit) and actions.can_spend(ActionType.MOVE):
        reach = reachable_hexes(catalog, battle, unit, budget=move_budget)
        home = deploy_anchor(battle, unit.side)
        best = None
        best_key = (10**9, 10**9)
        for key, cost in reach.items():
            if cost == 0:
                continue
            q, r = map(int, key.split(","))
            h = Hex(q, r)
            dist = axial_distance(h, home)
            in_home = 0 if hex_in_deploy(battle, unit.side, h) else 1
            cand = (in_home, dist, cost)
            if best is None or cand < best_key:
                best_key = cand
                best = (h, cost)
        if best:
            dest, cost = best
            path = find_path(catalog, battle, unit, dest, budget=move_budget)
            if path:
                is_dash = cost > unit.speed
                add(
                    "return_to_resupply",
                    "Dash home to rearm" if is_dash else "Return to deploy to rearm",
                    "move",
                    [{"type": "hex", "q": dest.q, "r": dest.r}],
                    {
                        "path": [p.to_dict() for p in path],
                        "movement_cost": cost,
                        "dash": is_dash,
                        "affected_hexes": [dest.to_dict()],
                        "enters_resupply": hex_in_deploy(battle, unit.side, dest),
                        "closes_on_resupply": True,
                    },
                    force=True,
                )

    # Out-of-signal drone autonomy menu only
    if unit.category == "drone" and unit.side == Side.FRIENDLY and not in_signal(battle, unit):
        # Autonomy: hold, move back toward signal, self-destruct, and defend_self (still shoot)
        limited = {}
        for oid, opt in options.items():
            if opt["subroutine"] in ("hold", "move", "self_destruct", "attack", "return_to_signal", "return_to_resupply"):
                limited[oid] = opt
        if not any(o["subroutine"] == "hold" for o in limited.values()):
            oid = stable_option_id("hold")
            limited[oid] = {
                "option_id": oid,
                "activation_id": battle.activation.activation_id,
                "actor_id": unit.unit_instance_id,
                "subroutine": "hold",
                "label": "Hold (autonomy)",
                "action_cost": "none",
                "target_refs": [],
                "preview": {"path": [], "movement_cost": 0, "affected_hexes": []},
                "issued_state_version": issued,
                "expires_with_activation": True,
            }
        # Add return_to_signal style move toward commander
        cmd = battle.commander()
        if cmd and actions.can_spend(ActionType.MOVE):
            reach = reachable_hexes(catalog, battle, unit, budget=move_budget)
            best = None
            best_dist = 999
            for key, cost in reach.items():
                if cost == 0:
                    continue
                q, r = map(int, key.split(","))
                h = Hex(q, r)
                d = axial_distance(h, cmd.position)
                if d < best_dist:
                    best_dist = d
                    best = (h, cost)
            if best:
                dest, cost = best
                path = find_path(catalog, battle, unit, dest, budget=move_budget)
                if path:
                    oid = stable_option_id("return_to_signal", {"affected_hexes": [dest.to_dict()]})
                    is_dash = cost > unit.speed
                    limited[oid] = {
                        "option_id": oid,
                        "activation_id": battle.activation.activation_id,
                        "actor_id": unit.unit_instance_id,
                        "subroutine": "return_to_signal",
                        "label": "Dash toward signal" if is_dash else "Return toward signal",
                        "action_cost": "move",
                        "target_refs": [{"type": "hex", "q": dest.q, "r": dest.r}],
                        "preview": {
                            "path": [p.to_dict() for p in path],
                            "movement_cost": cost,
                            "dash": is_dash,
                            "affected_hexes": [dest.to_dict()],
                        },
                        "issued_state_version": issued,
                        "expires_with_activation": True,
                    }
        return limited

    # Commander RAM abilities — always listed so the panel does not flicker; blocked_reason explains why
    if unit.category == "commander":
        from .state import commander_ram_abilities, signal_radius, within_commander_signal

        ally = unit.side
        enemy = Side.OPPOSITION if ally == Side.FRIENDLY else Side.FRIENDLY
        for aid in commander_ram_abilities(battle, unit):
            ability = catalog.abilities.get(aid)
            if not ability:
                continue
            blocked: str | None = None
            needs_target = aid in ("spoof_unit_location", "airstrike", "signal_jamming")
            if ability.once_per_battle and aid in unit.used_once_abilities:
                blocked = "Already used this battle"
            elif not actions.can_spend(ActionType.MINOR):
                blocked = "No minor action remaining"
            elif ability.ram_cost > (unit.ram_current or 0):
                blocked = f"Need {ability.ram_cost} RAM"
            elif aid == "targeting_assistance":
                drones = [u for u in battle.living_units(ally) if u.category == "drone"]
                in_sig = [u for u in drones if in_signal(battle, u)]
                if not drones:
                    blocked = "No living friendly drones"
                elif not in_sig:
                    blocked = "No friendly drones in signal"
            elif aid == "call_for_action":
                radius = signal_radius(unit)
                soldiers = [
                    u
                    for u in battle.living_units(ally)
                    if u.category == "soldier_squad"
                ]
                in_range = [u for u in soldiers if unit_within_radius(unit.position, u, radius)]
                if not soldiers:
                    blocked = "No living infantry"
                elif not in_range:
                    blocked = "No infantry in signal range"
            elif aid == "airstrike":
                painted = [
                    u
                    for u in battle.living_units(enemy)
                    if "painted" in u.statuses and u.category != "decoy"
                ]
                if not painted:
                    blocked = "Paint a target first"
            elif aid == "signal_jamming":
                jam_targets = [
                    u
                    for u in battle.living_units(enemy)
                    if u.category == "drone" and within_commander_signal(battle, u.position, side=unit.side)
                ]
                if not jam_targets:
                    blocked = "No opposition drone in signal"
            label = f"{ability.display_name} ({ability.ram_cost} RAM)"
            if blocked:
                label = f"{ability.display_name} — {blocked}"
            oid = f"ram:{aid}"
            options[oid] = {
                "option_id": oid,
                "activation_id": battle.activation.activation_id,
                "actor_id": unit.unit_instance_id,
                "subroutine": "ram_ability",
                "label": label,
                "action_cost": "minor",
                "target_refs": [],
                "preview": {
                    "path": [],
                    "movement_cost": 0,
                    "affected_hexes": [],
                    "ability_id": aid,
                    "ram_cost": ability.ram_cost,
                    "needs_target": needs_target and not blocked,
                    "disabled": bool(blocked),
                    "blocked_reason": blocked,
                    "risk_tags": [],
                },
                "issued_state_version": issued,
                "expires_with_activation": True,
            }

        # Dynamic 4th RAM ability when a support drone is in the army (friendly only)
        support = find_support_drone(battle, ally)
        if support and support.alive and unit.side == Side.FRIENDLY:
            if unit.embarked_in:
                leave = catalog.abilities.get("leave_support_drone")
                blocked = None if actions.can_spend(ActionType.MINOR) else "No minor action remaining"
                label = leave.display_name if leave else "Leave Support Drone"
                if blocked:
                    label = f"{label} — {blocked}"
                options["ram:leave_support_drone"] = {
                    "option_id": "ram:leave_support_drone",
                    "activation_id": battle.activation.activation_id,
                    "actor_id": unit.unit_instance_id,
                    "subroutine": "ram_ability",
                    "label": label,
                    "action_cost": "minor",
                    "target_refs": [],
                    "preview": {
                        "path": [],
                        "movement_cost": 0,
                        "affected_hexes": [],
                        "ability_id": "leave_support_drone",
                        "ram_cost": 0,
                        "needs_target": False,
                        "disabled": bool(blocked),
                        "blocked_reason": blocked,
                        "risk_tags": [],
                    },
                    "issued_state_version": issued,
                    "expires_with_activation": True,
                }
            else:
                call = catalog.abilities.get("call_support_drone")
                blocked = None
                if not actions.can_spend(ActionType.MINOR):
                    blocked = "No minor action remaining"
                elif not in_signal(battle, support):
                    blocked = "Support drone out of signal"
                label = call.display_name if call else "Call Support Drone"
                if blocked:
                    label = f"{label} — {blocked}"
                options["ram:call_support_drone"] = {
                    "option_id": "ram:call_support_drone",
                    "activation_id": battle.activation.activation_id,
                    "actor_id": unit.unit_instance_id,
                    "subroutine": "ram_ability",
                    "label": label,
                    "action_cost": "minor",
                    "target_refs": [],
                    "preview": {
                        "path": [],
                        "movement_cost": 0,
                        "affected_hexes": [],
                        "ability_id": "call_support_drone",
                        "ram_cost": 0,
                        "needs_target": False,
                        "disabled": bool(blocked),
                        "blocked_reason": blocked,
                        "risk_tags": [],
                    },
                    "issued_state_version": issued,
                    "expires_with_activation": True,
                }

    return options


def fallback_select(options: dict[str, dict], unit: UnitState, battle: BattleState | None = None) -> str:
    """Deterministic scoring of option menu."""
    if not options:
        raise ValueError("No options")

    tags: set[str] = set()
    focus_target_id: str | None = None
    if battle and unit.side == Side.FRIENDLY:
        for d in battle.directives or []:
            if not d.get("active"):
                continue
            if d.get("scope") == "global" or d.get("target_unit_id") == unit.unit_instance_id:
                tags.update(d.get("derived_tags") or [])
                for ref in d.get("target_refs") or []:
                    if isinstance(ref, dict) and ref.get("kind") == "unit":
                        focus_target_id = ref.get("unit_instance_id") or focus_target_id

    # Never walk past a legal shot/detonation: opposition always, friendly combat units unless holding
    combat_ready = bool({"frontline", "mobile_damage", "area_damage", "disposable"} & set(unit.roles))
    paint_order = "paint_target" in tags and "paint_target" in (unit.abilities or [])
    force_attack = (
        unit.side == Side.OPPOSITION
        or bool(tags & {"attack", "engage", "focus_fire"})
        or (combat_ready and not (tags & {"hold", "defensive"}))
    ) and not paint_order
    attacks = {
        oid: opt
        for oid, opt in options.items()
        if opt.get("subroutine") in ("attack", "self_destruct", "deploy_mine")
    }
    need_temple = bool(
        battle
        and not any(unit_contests_objective(battle, u) for u in battle.living_units(unit.side))
    )
    enter_moves = {
        oid: opt
        for oid, opt in options.items()
        if opt.get("subroutine") in ("move", "return_to_signal") and (opt.get("preview") or {}).get("enters_objective")
    }
    closing_moves = {
        oid: opt
        for oid, opt in options.items()
        if opt.get("subroutine") in ("move", "return_to_signal") and (opt.get("preview") or {}).get("closes_on_objective")
    }
    zone_attacks = {oid: opt for oid, opt in attacks.items() if _attack_target_in_objective(battle, opt)}
    suicides = {oid: opt for oid, opt in attacks.items() if opt.get("subroutine") == "self_destruct"}
    temple_kills = {**zone_attacks, **suicides}
    already_contesting = bool(battle and unit_contests_objective(battle, unit))
    holds = {oid: opt for oid, opt in options.items() if opt.get("subroutine") == "hold"}
    from ..content.loader import get_catalog
    from .resupply import must_return_to_resupply

    catalog = get_catalog()
    rearming = should_return_to_resupply(catalog, unit)
    combat_dry = must_return_to_resupply(catalog, unit)
    rtb_moves = {
        oid: opt
        for oid, opt in options.items()
        if opt.get("subroutine") == "return_to_resupply"
        or (
            opt.get("subroutine") in ("move", "return_to_signal")
            and (
                (opt.get("preview") or {}).get("enters_resupply")
                or (opt.get("preview") or {}).get("closes_on_resupply")
            )
        )
    }
    # Strike drones shoot whenever they can; empty ones fly home to rearm
    under_mines = {
        oid: opt
        for oid, opt in attacks.items()
        if opt.get("subroutine") == "deploy_mine" and (opt.get("preview") or {}).get("under_enemy")
    }
    gun_attacks = {
        oid: opt
        for oid, opt in attacks.items()
        if opt.get("subroutine") in ("attack", "self_destruct")
    }
    hold_mines = {
        oid: opt
        for oid, opt in attacks.items()
        if opt.get("subroutine") == "deploy_mine"
        and not (opt.get("preview") or {}).get("under_enemy")
        and not (opt.get("preview") or {}).get("in_own_deploy")
        and (
            (opt.get("preview") or {}).get("near_objective")
            or (opt.get("preview") or {}).get("on_approach")
        )
    }
    paint_opts = {
        oid: opt for oid, opt in options.items() if opt.get("subroutine") == "paint_target"
    }
    is_sapper = "deploy_mine" in (unit.abilities or [])
    disposable_bomber = _is_disposable_bomber(unit)
    push_orders = bool(tags & {"advance", "objective", "center", "engage", "attack", "focus_fire"})
    moves_spent = int(getattr(battle.activation.actions, "moves_spent", 0) or 0) if battle and battle.activation else 0
    already_moved = moves_spent >= 1
    if paint_order and paint_opts:
        if focus_target_id:
            focused_paint = {
                oid: opt
                for oid, opt in paint_opts.items()
                if (opt.get("preview") or {}).get("target_unit_id") == focus_target_id
            }
            options = focused_paint or paint_opts
        else:
            options = paint_opts
    elif paint_order and focus_target_id and battle:
        goal = battle.units.get(focus_target_id)
        if goal and goal.alive:
            closing_on_focus = {
                oid: opt
                for oid, opt in options.items()
                if opt.get("subroutine") in ("move", "return_to_signal")
                and _closes_on_enemy(unit.position, Hex(**opt["preview"]["affected_hexes"][0]), [goal])
            }
            if closing_on_focus:
                options = closing_on_focus
    elif disposable_bomber and suicides:
        options = suicides
    elif disposable_bomber:
        closing_on_foe = {
            oid: opt
            for oid, opt in options.items()
            if opt.get("subroutine") in ("move", "return_to_signal")
            and (opt.get("preview") or {}).get("closes_on_enemy")
        }
        detonation_moves = {
            oid: opt
            for oid, opt in options.items()
            if opt.get("subroutine") in ("move", "return_to_signal")
            and (opt.get("preview") or {}).get("detonation_would_hit")
        }
        if detonation_moves:
            options = detonation_moves
        elif closing_on_foe:
            options = closing_on_foe
    elif _is_striker(unit) and attacks:
        options = attacks
    elif (combat_dry or (rearming and not gun_attacks)) and rtb_moves:
        # Empty magazines alone must not suppress gun attacks (anti-armor rifle after missiles).
        options = rtb_moves
    elif already_moved and (under_mines or gun_attacks):
        # Action economy: after one Move, finish with mine-under-enemy or guns — never double-dash.
        options = {**under_mines, **gun_attacks} or under_mines or gun_attacks
    elif is_sapper and under_mines:
        options = {**under_mines, **gun_attacks} if gun_attacks else under_mines
    elif is_sapper and push_orders and (enter_moves or closing_moves) and not under_mines:
        # Push: advance and/or shoot; preemptive mines only on approach / objective.
        options = {**enter_moves, **closing_moves, **gun_attacks, **hold_mines} or {
            **closing_moves,
            **enter_moves,
            **gun_attacks,
        }
    elif need_temple and enter_moves:
        options = {**enter_moves, **temple_kills} if temple_kills else enter_moves
    elif need_temple and closing_moves:
        options = {**closing_moves, **temple_kills} if temple_kills else closing_moves
    elif already_contesting and not attacks and holds:
        options = holds
    elif force_attack and attacks:
        options = attacks

    scored: list[tuple[int, str, str]] = []
    for oid, opt in options.items():
        sub = opt["subroutine"]
        score = 0
        label = str(opt.get("label", ""))
        preview = opt.get("preview") or {}
        if (preview.get("disabled") or preview.get("blocked_reason")) and sub == "ram_ability":
            score = -50
        elif sub == "deploy_mine":
            # Combat Engineers: under-enemy highest; preemptive only on approach / objective.
            is_sapper = "deploy_mine" in (unit.abilities or [])
            push = bool(tags & {"advance", "objective", "center", "engage", "attack", "focus_fire"})
            if preview.get("under_enemy"):
                score = 220 if is_sapper else 130
            elif preview.get("in_own_deploy"):
                score = -40
            elif preview.get("near_objective"):
                score = 125 if is_sapper else 70
            elif preview.get("on_approach"):
                score = 110 if is_sapper else 55
            else:
                score = 20 if is_sapper else 40
            if push and not preview.get("under_enemy") and not (
                preview.get("near_objective") or preview.get("on_approach")
            ):
                score -= 80
            if tags & {"hold", "defensive"} and preview.get("near_objective"):
                score += 15
        elif sub == "attack":
            score = 120 if unit.side == Side.OPPOSITION else 80
            if "deploy_mine" in (unit.abilities or []):
                # Guns beat empty mines / random shuffle; under-enemy still wins above.
                score += 15
            if already_moved:
                score += 90
            if "area_damage" in unit.roles or "mobile_damage" in unit.roles:
                score += 10
            if "commander" in label.lower() or "Drone Commander" in label:
                score += 40
            if tags & {"attack", "engage", "focus_fire", "advance"}:
                score += 35
            if focus_target_id and preview.get("target_unit_id") == focus_target_id:
                score += 50
            # Anti-armor doctrine: heavy cannon vs armored targets
            weapon_id = preview.get("weapon_id")
            tid = preview.get("target_unit_id")
            tgt = battle.units.get(tid) if battle and tid else None
            if weapon_id in ("heavy_cannon", "heavy_cannon_12") and tgt and int(tgt.armor or 0) >= 14:
                score += 25
        elif sub == "self_destruct":
            # Only offered when the blast hits an enemy; prioritize clustered targets (AOE value)
            score = 200 if "disposable" in unit.roles else 80
            enemy_models = int(preview.get("enemy_models_in_blast") or 0)
            score += 40 * max(0, enemy_models - 1)
            if preview.get("friendly_fire"):
                friendly_models = int(preview.get("friendly_models_in_blast") or 0)
                enemy_models = int(preview.get("enemy_models_in_blast") or 0)
                score -= 40 + 25 * friendly_models
                if any((f or {}).get("is_commander") for f in (preview.get("friendlies_in_blast") or [])):
                    score -= 120
                if enemy_models <= friendly_models:
                    score -= 60
                if any((e or {}).get("is_commander") for e in (preview.get("enemies_in_blast") or [])):
                    score += 80
        elif sub == "paint_target":
            score = 65
            if "paint_target" in tags:
                score = 220
            if tags & {"attack", "engage", "focus_fire"}:
                score += 25
            if focus_target_id and preview.get("target_unit_id") == focus_target_id:
                score += 80
        elif sub in ("move", "return_to_signal", "return_to_resupply"):
            score = 50
            if disposable_bomber:
                enemy_models = int(preview.get("detonation_enemy_models") or 0)
                if preview.get("detonation_would_hit"):
                    score = 280 + enemy_models * 35
                elif preview.get("closes_on_enemy"):
                    score = 140
                else:
                    score = 30
                if push_orders and preview.get("enters_objective"):
                    score += 15
            if already_moved and gun_attacks:
                score -= 100
            if sub == "return_to_signal":
                score = 90
            if sub == "return_to_resupply":
                score = 180
            if preview.get("enters_resupply"):
                score += 80
            if preview.get("closes_on_resupply") and not attacks:
                score += 50
            if tags & {"advance", "objective", "center", "engage"}:
                score += 20
            if "deploy_mine" in (unit.abilities or []) and tags & {"advance", "objective", "center", "engage"}:
                # Engineers under push orders: advancing beats empty deploy-zone mines.
                if preview.get("closes_on_objective") or preview.get("enters_objective"):
                    score += 100
            if tags & {"hold", "defensive"}:
                score -= 15
            if tags & {"commander_protective", "screen"}:
                score += 10
            if preview.get("enters_objective"):
                score += 35
            if preview.get("closes_on_objective"):
                score += 20
            if need_temple and preview.get("closes_on_objective"):
                score += 40
            if need_temple and preview.get("enters_objective"):
                score += 90
        elif sub == "ram_ability":
            score = 60
        elif sub == "hold":
            score = 10
            if already_contesting and not attacks and not rearming:
                score = 95
            if tags & {"hold", "defensive"}:
                score += 70
            if tags & {"advance", "engage", "attack", "focus_fire"}:
                score -= 5
        scored.append((score, label, oid))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return scored[0][2]
