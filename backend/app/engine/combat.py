"""Combat resolution: attack, damage, AOE, destruction."""

from __future__ import annotations

from uuid import uuid4

from ..content.loader import ContentCatalog
from ..domain.enums import ActionType, BattleStatus, Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance, hexes_in_radius
from .formation import model_can_shoot, pick_volley_target_model, plan_firing_repositions
from .field_effects import find_support_drone, resolve_call_support_drone, resolve_leave_support_drone
from .state import (
    BattleState,
    UnitState,
    attack_modifier,
    combat_profile,
    effective_defense,
    evaluate_terminal,
    has_line_of_sight,
    in_signal,
    is_targetable,
    signal_radius,
    unit_within_radius,
    within_commander_signal,
)


def resolve_attack(
    catalog: ContentCatalog,
    battle: BattleState,
    attacker: UnitState,
    weapon_id: str,
    target: UnitState,
    *,
    target_model_id: str | None = None,
    spend_action: bool = True,
) -> list[DomainEvent]:
    if not is_targetable(target):
        raise ValueError("Target cannot be engaged")
    profile = combat_profile(battle, attacker)
    if weapon_id not in profile.weapons and weapon_id not in attacker.weapons:
        raise ValueError("Weapon not equipped")
    weapon = catalog.weapons[weapon_id]
    if weapon.ammo is not None:
        remaining = attacker.ammo.get(weapon_id, weapon.ammo)
        if remaining <= 0:
            raise ValueError("No ammunition")

    # Preferred opening model; if already gone, fall through to any living model
    preferred_id = target_model_id
    tmodel = None
    if preferred_id:
        tmodel = next((m for m in target.living_models if m.model_id == preferred_id), None)
    if not tmodel:
        tmodel = target.leader_model() or next(iter(target.living_models), None)
        preferred_id = tmodel.model_id if tmodel else preferred_id
    if not tmodel and target.category != "decoy":
        raise ValueError("No living target model")

    events: list[DomainEvent] = []
    aiming_paths: list[dict] = []
    aims = [target.model_position(m) for m in target.living_models] if target.category != "decoy" else [target.position]
    squad_volley = attacker.category == "soldier_squad" and not bool(weapon.area) and weapon.ammo is None

    # Squad rifles: models without a shot reposition, then volley.
    # Grenades / ammo weapons: one thrower, not ten overlapping blasts.
    saved_positions: list[tuple] = []
    if attacker.category == "soldier_squad" and target.category != "decoy":
        aim_plans = plan_firing_repositions(catalog, battle, attacker, aims, weapon.range)
        if aim_plans:
            if not squad_volley:
                thrower_id = (attacker.leader_model() or attacker.living_models[0]).model_id
                aim_plans = [p for p in aim_plans if p.model_id == thrower_id] or aim_plans[:1]
            saved_positions = [(m, m.position) for m in attacker.models]
            for plan in aim_plans:
                model = next((m for m in attacker.models if m.model_id == plan.model_id), None)
                if model and model.alive:
                    model.position = plan.destination
                aiming_paths.append(
                    {
                        "model_id": plan.model_id,
                        "path": [p.to_dict() for p in plan.path],
                        "to": plan.destination.to_dict(),
                    }
                )
            attacker.sync_position_from_leader()
            aims = [target.model_position(m) for m in target.living_models]

    if squad_volley:
        shooters = list(attacker.living_models)
    else:
        thrower = None
        if aiming_paths:
            mid = aiming_paths[0]["model_id"]
            thrower = next((m for m in attacker.living_models if m.model_id == mid), None)
        thrower = thrower or attacker.leader_model() or next(iter(attacker.living_models), None)
        shooters = [thrower] if thrower else list(attacker.models[:1])
    legal_shooters = []
    for sm in shooters:
        from_hex = attacker.model_position(sm)
        if any(model_can_shoot(catalog, battle, from_hex, th, weapon.range) for th in aims):
            legal_shooters.append(sm)
    if not legal_shooters and target.category != "decoy":
        for m, pos in saved_positions:
            m.position = pos
        if saved_positions:
            attacker.sync_position_from_leader()
        raise ValueError("Target out of range or no line of sight")

    # Confirm at least one shooter has a hittable living model before spending the action
    if target.category != "decoy":
        can_fire = False
        for sm in legal_shooters:
            from_hex = attacker.model_position(sm)
            victim = pick_volley_target_model(
                catalog, battle, from_hex, target, weapon.range, preferred_model_id=preferred_id
            )
            if victim and model_can_shoot(catalog, battle, from_hex, target.model_position(victim), weapon.range):
                can_fire = True
                break
        if not can_fire:
            for m, pos in saved_positions:
                m.position = pos
            if saved_positions:
                attacker.sync_position_from_leader()
            raise ValueError("Target out of range or no line of sight")

    if aiming_paths:
        events.append(
            DomainEvent(
                type="unit_moved",
                actor_id=attacker.unit_instance_id,
                payload={
                    "reason": "aiming_reposition",
                    "path": aiming_paths[0]["path"],
                    "to": attacker.position.to_dict(),
                    "model_paths": aiming_paths,
                    "animation": {
                        "type": "squad_aim_move",
                        "model_paths": aiming_paths,
                        "path": aiming_paths[0]["path"],
                    },
                },
            )
        )
    if spend_action and battle.activation and battle.activation.actor_id == attacker.unit_instance_id:
        used = battle.activation.actions.spend(ActionType.STANDARD)
        events.append(
            DomainEvent(
                type="action_spent",
                actor_id=attacker.unit_instance_id,
                payload={"action": used.value, "for": "attack", "weapon_id": weapon_id},
            )
        )

    if weapon.ammo is not None:
        attacker.ammo[weapon_id] = attacker.ammo.get(weapon_id, weapon.ammo) - 1
        events.append(
            DomainEvent(
                type="resource_changed",
                actor_id=attacker.unit_instance_id,
                payload={"resource": "ammo", "weapon_id": weapon_id, "remaining": attacker.ammo[weapon_id]},
            )
        )

    # Spoof decoys are revealed and removed by any committed attack
    if target.category == "decoy":
        from_hex = attacker.model_position(attacker.leader_model())
        events.append(
            DomainEvent(
                type="weapon_fired",
                actor_id=attacker.unit_instance_id,
                payload={
                    "weapon_id": weapon_id,
                    "target_id": target.unit_instance_id,
                    "attack_count": 1,
                    "shots": [
                        {
                            "attacker_model": legal_shooters[0].model_id if legal_shooters else "m1",
                            "from": from_hex.to_dict(),
                            "to": target.position.to_dict(),
                        }
                    ],
                    "animation": {
                        "type": "weapon_fire",
                        "from": from_hex.to_dict(),
                        "to": target.position.to_dict(),
                    },
                },
            )
        )
        target.alive = False
        for m in target.models:
            m.alive = False
            m.hp = 0
            m.position = None
        events.append(
            DomainEvent(
                type="decoy_revealed",
                actor_id=target.unit_instance_id,
                payload={
                    "source_unit_id": next((s for s in target.statuses if s.startswith("spoof_of:")), None),
                    "position": target.position.to_dict(),
                    "animation": {"type": "damage_flash", "at": target.position.to_dict()},
                },
            )
        )
        battle.commit_rng(battle.rng())
        return events

    rng = battle.rng()
    shot_anims: list[dict] = []
    combat_events: list[DomainEvent] = []
    hit_any = False
    opening_model_id = preferred_id

    for model in legal_shooters:
        from_hex = attacker.model_position(model)
        if not target.alive or not target.living_models:
            break
        victim = pick_volley_target_model(
            catalog,
            battle,
            from_hex,
            target,
            weapon.range,
            preferred_model_id=preferred_id,
        )
        if not victim or not victim.alive:
            break
        # Prefer declared model only while it still lives and is hittable
        if preferred_id and victim.model_id != preferred_id:
            preferred_id = None
        aim_hex = target.model_position(victim)
        if not model_can_shoot(catalog, battle, from_hex, aim_hex, weapon.range):
            # Shooter can hit some other living model — pick without preference
            victim = pick_volley_target_model(catalog, battle, from_hex, target, weapon.range, preferred_model_id=None)
            if not victim or not victim.alive:
                continue
            aim_hex = target.model_position(victim)
            if not model_can_shoot(catalog, battle, from_hex, aim_hex, weapon.range):
                continue

        shot_anims.append(
            {
                "attacker_model": model.model_id,
                "from": from_hex.to_dict(),
                "to": aim_hex.to_dict(),
                "target_model": victim.model_id,
            }
        )

        dice, total = rng.roll_nd6(3)
        attack_total = total + profile.attack + attack_modifier(battle, attacker, target)
        defense = effective_defense(catalog, battle, target, at_hex=aim_hex)
        hit = attack_total >= defense
        combat_events.append(
            DomainEvent(
                type="attack_resolved",
                actor_id=attacker.unit_instance_id,
                payload={
                    "attacker_model": model.model_id,
                    "target_id": target.unit_instance_id,
                    "target_model_id": victim.model_id,
                    "dice": dice,
                    "modifier": attacker.attack + attack_modifier(battle, attacker, target),
                    "total": attack_total,
                    "defense": defense,
                    "hit": hit,
                    "rng_index": rng.index,
                    "animation": {
                        "type": "weapon_fire",
                        "from": from_hex.to_dict(),
                        "to": aim_hex.to_dict(),
                    },
                },
            )
        )
        if not hit:
            continue
        hit_any = True
        if weapon.area and weapon.area > 0:
            combat_events.extend(
                _resolve_aoe(catalog, battle, attacker, weapon_id, weapon.damage, weapon.area, aim_hex, rng)
            )
        else:
            combat_events.extend(
                _apply_damage(
                    catalog,
                    battle,
                    attacker,
                    target,
                    weapon.damage,
                    rng,
                    victim=victim,
                    weapon_tags=list(weapon.tags or []),
                )
            )
        # Clear preferred if that model was just removed
        if preferred_id and not any(m.model_id == preferred_id and m.alive for m in target.models):
            preferred_id = None

    if not shot_anims:
        # Should be unreachable after can_fire gate; keep battle consistent
        shot_anims.append(
            {
                "attacker_model": legal_shooters[0].model_id,
                "from": attacker.model_position(legal_shooters[0]).to_dict(),
                "to": target.position.to_dict(),
                "target_model": opening_model_id,
            }
        )

    events.append(
        DomainEvent(
            type="weapon_fired",
            actor_id=attacker.unit_instance_id,
            payload={
                "weapon_id": weapon_id,
                "target_id": target.unit_instance_id,
                "target_model_id": opening_model_id,
                "attack_count": len(shot_anims),
                "shots": shot_anims,
                "aiming_paths": aiming_paths,
                "animation": {
                    "type": "squad_volley" if len(shot_anims) > 1 else "weapon_fire",
                    "from": shot_anims[0]["from"],
                    "to": shot_anims[0]["to"],
                    "shots": shot_anims,
                    "aiming_paths": aiming_paths,
                },
            },
        )
    )
    events.extend(combat_events)

    battle.commit_rng(rng)
    if not hit_any:
        events.append(
            DomainEvent(
                type="attack_resolved",
                actor_id=attacker.unit_instance_id,
                payload={
                    "summary": "all_missed",
                    "target_id": target.unit_instance_id,
                    "target_model_id": opening_model_id,
                },
            )
        )

    terminal = evaluate_terminal(battle)
    if terminal:
        battle.status = terminal
        battle.result = terminal.value
        events.append(
            DomainEvent(
                type="battle_completed",
                payload={"status": terminal.value, "result": terminal.value},
            )
        )
    return events


def _apply_damage(
    catalog,
    battle,
    attacker,
    target: UnitState,
    damage_mod: int,
    rng,
    victim=None,
    *,
    weapon_tags: list[str] | None = None,
) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    if victim is None:
        victim = next((m for m in target.models if m.alive), None)
    if not victim or not victim.alive:
        return events
    dice, total = rng.roll_nd6(3)
    dmg_total = total + damage_mod
    armor = int(target.armor or 0)
    if dmg_total > armor:
        dealt = dmg_total - armor
    else:
        dealt = 0
    victim.hp = max(0, victim.hp - dealt)
    at_hex = target.model_position(victim)
    events.append(
        DomainEvent(
            type="damage_applied",
            actor_id=attacker.unit_instance_id,
            payload={
                "target_id": target.unit_instance_id,
                "model_id": victim.model_id,
                "dice": dice,
                "modifier": damage_mod,
                "total": dmg_total,
                "armor": target.armor,
                "dealt": dealt,
                "remaining_hp": victim.hp,
                "animation": {"type": "damage_number", "amount": dealt, "at": at_hex.to_dict()},
            },
        )
    )
    if victim.hp <= 0:
        victim.alive = False
        victim.hp = 0
        victim.position = None
        events.append(
            DomainEvent(
                type="model_destroyed",
                payload={"unit_id": target.unit_instance_id, "model_id": victim.model_id},
            )
        )
        target.sync_position_from_leader()
    if not target.living_models:
        target.alive = False
        events.append(
            DomainEvent(
                type="unit_defeated",
                payload={"unit_id": target.unit_instance_id, "side": target.side.value, "animation": {"type": "unit_defeated"}},
            )
        )
        from .objective import drop_flags_for_unit

        events.extend(drop_flags_for_unit(battle, target.unit_instance_id))
        if target.definition_id == "friendly_commander_support_drone" and target.embarked_commander_id:
            from .field_effects import resolve_embarked_drone_destroyed

            events.extend(resolve_embarked_drone_destroyed(catalog, battle, target))
    return events


def _resolve_aoe(catalog, battle: BattleState, attacker, weapon_id, damage_mod, area, impact: Hex, rng) -> list[DomainEvent]:
    events: list[DomainEvent] = [
        DomainEvent(
            type="attack_resolved",
            actor_id=attacker.unit_instance_id,
            payload={"aoe": area, "impact": impact.to_dict(), "weapon_id": weapon_id},
        )
    ]
    affected = hexes_in_radius(impact, area, battle.width, battle.height)
    affected_keys = {f"{h.q},{h.r}" for h in affected}
    for unit in list(battle.units.values()):
        if not unit.alive:
            continue
        for model in list(unit.living_models):
            mpos = unit.model_position(model)
            if f"{mpos.q},{mpos.r}" not in affected_keys:
                continue
            dice, total = rng.roll_nd6(3)
            dmg_total = total + damage_mod
            armor = int(unit.armor or 0)
            dealt = max(0, dmg_total - armor) if dmg_total > armor else 0
            model.hp = max(0, model.hp - dealt)
            events.append(
                DomainEvent(
                    type="damage_applied",
                    actor_id=attacker.unit_instance_id,
                    payload={
                        "target_id": unit.unit_instance_id,
                        "model_id": model.model_id,
                        "dice": dice,
                        "modifier": damage_mod,
                        "total": dmg_total,
                        "armor": unit.armor,
                        "dealt": dealt,
                        "remaining_hp": model.hp,
                        "aoe": True,
                        "animation": {"type": "damage_number", "amount": dealt, "at": mpos.to_dict()},
                    },
                )
            )
            if model.hp <= 0:
                model.alive = False
                model.position = None
                events.append(DomainEvent(type="model_destroyed", payload={"unit_id": unit.unit_instance_id, "model_id": model.model_id}))
        if unit.alive:
            unit.sync_position_from_leader()
        if not unit.living_models:
            unit.alive = False
            events.append(DomainEvent(type="unit_defeated", payload={"unit_id": unit.unit_instance_id, "side": unit.side.value}))
            from .objective import drop_flags_for_unit

            events.extend(drop_flags_for_unit(battle, unit.unit_instance_id))
    return events


def self_destruct_ability_for_unit(catalog: ContentCatalog, unit: UnitState):
    for aid in unit.abilities:
        if aid.startswith("self_destruct"):
            return catalog.abilities.get(aid)
    return catalog.abilities.get("self_destruct")


def resolve_self_destruct(catalog: ContentCatalog, battle: BattleState, unit: UnitState) -> list[DomainEvent]:
    events: list[DomainEvent] = []
    if battle.activation and battle.activation.actor_id == unit.unit_instance_id:
        used = battle.activation.actions.spend(ActionType.MINOR)
        events.append(DomainEvent(type="action_spent", actor_id=unit.unit_instance_id, payload={"action": used.value, "for": "self_destruct"}))
    ability = self_destruct_ability_for_unit(catalog, unit) or catalog.abilities["self_destruct"]
    rng = battle.rng()
    impact = unit.position
    events.extend(_resolve_aoe(catalog, battle, unit, ability.id, ability.damage or 10, ability.area or 1, impact, rng))
    # Destroy self
    for m in unit.models:
        m.alive = False
        m.hp = 0
    unit.alive = False
    events.append(DomainEvent(type="unit_defeated", payload={"unit_id": unit.unit_instance_id, "side": unit.side.value, "reason": "self_destruct"}))
    from .objective import drop_flags_for_unit

    events.extend(drop_flags_for_unit(battle, unit.unit_instance_id))
    battle.commit_rng(rng)
    terminal = evaluate_terminal(battle)
    if terminal:
        battle.status = terminal
        battle.result = terminal.value
        events.append(DomainEvent(type="battle_completed", payload={"status": terminal.value}))
    return events


def _ram_ally_enemy(commander: UnitState) -> tuple[Side, Side]:
    ally = commander.side
    enemy = Side.OPPOSITION if ally == Side.FRIENDLY else Side.FRIENDLY
    return ally, enemy


def _commander_has_ram_ability(battle: BattleState, commander: UnitState, ability_id: str) -> bool:
    from .state import commander_ram_abilities

    return ability_id in commander_ram_abilities(battle, commander)


def _validate_ram_cast(
    battle: BattleState,
    commander: UnitState,
    ability_id: str,
    target_hex: Hex | None,
    target_unit_id: str | None,
) -> None:
    """Raise before spending RAM/actions if the cast cannot resolve."""
    ally, enemy = _ram_ally_enemy(commander)
    if ability_id == "targeting_assistance":
        if not any(u.category == "drone" and in_signal(battle, u) for u in battle.living_units(ally)):
            raise ValueError("No allied drones in signal for Targeting Assistance")
    elif ability_id == "call_for_action":
        radius = signal_radius(commander)
        if not any(
            u.category == "soldier_squad" and unit_within_radius(commander.position, u, radius)
            for u in battle.living_units(ally)
        ):
            raise ValueError("No allied soldier units in signal for Call for Action")
    elif ability_id == "airstrike":
        if not target_unit_id or target_unit_id not in battle.units:
            raise ValueError("Airstrike requires a painted enemy unit")
        painted = battle.units[target_unit_id]
        if painted.side != enemy or not painted.alive or painted.category == "decoy":
            raise ValueError("Airstrike requires a living enemy target")
        if "painted" not in painted.statuses:
            raise ValueError("Airstrike requires a painted target")
    elif ability_id == "signal_jamming":
        if not target_unit_id or target_unit_id not in battle.units:
            raise ValueError("Signal Jamming requires an enemy drone within signal")
        tu = battle.units[target_unit_id]
        if tu.side != enemy or tu.category != "drone" or not tu.alive:
            raise ValueError("Signal Jamming targets an enemy drone")
        if not within_commander_signal(battle, tu.position, side=commander.side):
            raise ValueError("Target drone must be within commander signal range")
    elif ability_id == "spoof_unit_location":
        if not target_unit_id or target_unit_id not in battle.units:
            raise ValueError("Spoof requires an allied unit in signal")
        if target_hex is None:
            raise ValueError("Spoof requires a destination hex")
        source = battle.units[target_unit_id]
        if source.side != ally or source.category in ("commander", "decoy") or not source.alive:
            raise ValueError("Spoof source must be a living allied non-commander unit")
        if not in_signal(battle, source):
            raise ValueError("Spoof source must be in signal range")
        if axial_distance(commander.position, target_hex) > signal_radius(commander):
            raise ValueError("Spoof destination must be within signal range")
        key = f"{target_hex.q},{target_hex.r}"
        if key in battle.occupancy():
            raise ValueError("Spoof destination is occupied")
        if target_hex.q < 0 or target_hex.r < 0 or target_hex.q >= battle.width or target_hex.r >= battle.height:
            raise ValueError("Spoof destination out of bounds")
    elif ability_id == "call_support_drone":
        support = find_support_drone(battle, ally)
        if not support or not support.alive:
            raise ValueError("No support drone in battle")
        if commander.embarked_in:
            raise ValueError("Already aboard support drone")
        if not in_signal(battle, support):
            raise ValueError("Support drone is out of signal — move closer before calling")
    elif ability_id == "leave_support_drone":
        if not commander.embarked_in:
            raise ValueError("Not aboard support drone")
    elif ability_id not in ("defense_matrix", "satellite_sweep"):
        raise ValueError(f"Unknown RAM ability {ability_id}")


def resolve_ram_ability(
    catalog: ContentCatalog,
    battle: BattleState,
    commander: UnitState,
    ability_id: str,
    target_hex: Hex | None = None,
    target_unit_id: str | None = None,
) -> list[DomainEvent]:
    if not _commander_has_ram_ability(battle, commander, ability_id) and ability_id not in (
        "call_support_drone",
        "leave_support_drone",
    ):
        raise ValueError("Ability not selected in prep")
    ability = catalog.abilities[ability_id]
    ally, enemy = _ram_ally_enemy(commander)
    if ability.ram_cost > (commander.ram_current or 0):
        raise ValueError("Insufficient RAM")
    if ability.once_per_battle and ability_id in commander.used_once_abilities:
        raise ValueError("Ability already used this battle")
    _validate_ram_cast(battle, commander, ability_id, target_hex, target_unit_id)

    events: list[DomainEvent] = []
    if battle.activation and battle.activation.actor_id == commander.unit_instance_id:
        used = battle.activation.actions.spend(ActionType.MINOR)
        events.append(DomainEvent(type="action_spent", actor_id=commander.unit_instance_id, payload={"action": used.value, "for": ability_id}))

    commander.ram_current = (commander.ram_current or 0) - ability.ram_cost
    events.append(
        DomainEvent(
            type="resource_changed",
            actor_id=commander.unit_instance_id,
            payload={"resource": "ram", "remaining": commander.ram_current, "capacity": commander.ram_capacity},
        )
    )

    if ability_id == "defense_matrix":
        if "defense_matrix" not in commander.statuses:
            commander.statuses.append("defense_matrix")
        events.append(DomainEvent(type="status_applied", payload={"unit_id": commander.unit_instance_id, "status": "defense_matrix", "defense_bonus": 4}))
    elif ability_id == "targeting_assistance":
        # Spec: all allied drones currently in signal gain +2 Attack through end of round
        buffed: list[str] = []
        for tu in battle.living_units(ally):
            if tu.category != "drone":
                continue
            if not in_signal(battle, tu):
                continue
            if "targeting_assisted" not in tu.statuses:
                tu.statuses.append("targeting_assisted")
            buffed.append(tu.unit_instance_id)
            events.append(DomainEvent(type="status_applied", payload={"unit_id": tu.unit_instance_id, "status": "targeting_assisted", "attack_bonus": 2}))
        if not buffed:
            raise ValueError("No allied drones in signal for Targeting Assistance")
    elif ability_id == "satellite_sweep":
        # Reveal/remove decoys and mark enemies as revealed (clears stealth) through end of round
        revealed_ids: list[str] = []
        for u in list(battle.units.values()):
            if u.alive and u.category == "decoy" and u.side == ally:
                u.alive = False
                for m in u.models:
                    m.alive = False
                    m.hp = 0
                events.append(DomainEvent(type="decoy_revealed", actor_id=u.unit_instance_id, payload={"reason": "satellite_sweep"}))
            elif u.alive and u.side == enemy:
                u.statuses = [s for s in u.statuses if s != "stealthed"]
                if "revealed" not in u.statuses:
                    u.statuses.append("revealed")
                revealed_ids.append(u.unit_instance_id)
        from .mines import reveal_enemy_mines_satellite

        events.extend(reveal_enemy_mines_satellite(battle, commander.side))
        events.append(
            DomainEvent(
                type="status_applied",
                payload={"status": "satellite_sweep", "revealed": revealed_ids},
            )
        )
    elif ability_id == "airstrike":
        if ability_id in commander.used_once_abilities:
            raise ValueError("Airstrike already used")
        # Spec: must target a painted unit (impact hex from that unit)
        if not target_unit_id or target_unit_id not in battle.units:
            raise ValueError("Airstrike requires a painted enemy unit")
        painted = battle.units[target_unit_id]
        if painted.side != enemy or not painted.alive or painted.category == "decoy":
            raise ValueError("Airstrike requires a living enemy target")
        if "painted" not in painted.statuses:
            raise ValueError("Airstrike requires a painted target")
        commander.used_once_abilities.append(ability_id)
        impact = painted.position
        rng = battle.rng()
        events.extend(_resolve_aoe(catalog, battle, commander, "airstrike", ability.damage or 12, ability.area or 3, impact, rng))
        battle.commit_rng(rng)
        terminal = evaluate_terminal(battle)
        if terminal:
            battle.status = terminal
            battle.result = terminal.value
            events.append(DomainEvent(type="battle_completed", payload={"status": terminal.value}))
    elif ability_id == "spoof_unit_location":
        if not target_unit_id or target_unit_id not in battle.units:
            raise ValueError("Spoof requires a friendly unit in signal")
        if target_hex is None:
            raise ValueError("Spoof requires a destination hex")
        source = battle.units[target_unit_id]
        if source.side != Side.FRIENDLY or source.category in ("commander", "decoy") or not source.alive:
            raise ValueError("Spoof source must be a living friendly non-commander unit")
        if not in_signal(battle, source):
            raise ValueError("Spoof source must be in signal range")
        radius = signal_radius(commander)
        if axial_distance(commander.position, target_hex) > radius:
            raise ValueError("Spoof destination must be within signal range")
        # Destination must be empty of real units
        occ = battle.occupancy()
        key = f"{target_hex.q},{target_hex.r}"
        if key in occ:
            raise ValueError("Spoof destination is occupied")
        if target_hex.q < 0 or target_hex.r < 0 or target_hex.q >= battle.width or target_hex.r >= battle.height:
            raise ValueError("Spoof destination out of bounds")
        decoy_id = f"decoy-{uuid4().hex[:8]}"
        decoy = UnitState(
            unit_instance_id=decoy_id,
            definition_id=source.definition_id,
            display_name=f"{source.display_name} (spoof)",
            side=ally,
            category="decoy",
            roles=list(source.roles),
            asset_set_id=source.asset_set_id,
            position=Hex(target_hex.q, target_hex.r),
            speed=0,
            attack=0,
            defense=source.defense,
            armor=source.armor,
            models=[],  # no HP — removed on any attack
            weapons=[],
            abilities=[],
            movement_traits=list(source.movement_traits),
            statuses=[f"spoof_of:{source.unit_instance_id}", "decoy"],
            alive=True,
        )
        battle.units[decoy_id] = decoy
        events.append(
            DomainEvent(
                type="decoy_created",
                actor_id=commander.unit_instance_id,
                payload={
                    "decoy_id": decoy_id,
                    "source_unit_id": source.unit_instance_id,
                    "position": target_hex.to_dict(),
                    "asset_set_id": source.asset_set_id,
                    "display_name": decoy.display_name,
                },
            )
        )
    elif ability_id == "signal_jamming":
        if not target_unit_id or target_unit_id not in battle.units:
            raise ValueError("Signal Jamming requires an enemy drone within signal")
        tu = battle.units[target_unit_id]
        if tu.side != enemy or tu.category != "drone" or not tu.alive:
            raise ValueError("Signal Jamming targets an enemy drone")
        if not within_commander_signal(battle, tu.position, side=commander.side):
            raise ValueError("Target drone must be within commander signal range")
        if "jammed" not in tu.statuses:
            tu.statuses.append("jammed")
        events.append(DomainEvent(type="status_applied", payload={"unit_id": target_unit_id, "status": "jammed", "attack_penalty": 2}))
    elif ability_id == "call_for_action":
        # Spec: all allied soldier units in signal gain +2 Speed through end of round
        buffed: list[str] = []
        for tu in battle.living_units(ally):
            if tu.category != "soldier_squad" or not tu.alive:
                continue
            cmd = commander
            if not unit_within_radius(cmd.position, tu, signal_radius(cmd)):
                continue
            if "call_for_action" not in tu.statuses:
                tu.speed = tu.speed + 2
                tu.statuses.append("call_for_action")
            buffed.append(tu.unit_instance_id)
            events.append(
                DomainEvent(
                    type="status_applied",
                    payload={"unit_id": tu.unit_instance_id, "status": "call_for_action", "speed_bonus": 2},
                )
            )
        if not buffed:
            raise ValueError("No allied soldier units in signal for Call for Action")
    elif ability_id == "call_support_drone":
        events.extend(resolve_call_support_drone(catalog, battle, commander))
    elif ability_id == "leave_support_drone":
        events.extend(resolve_leave_support_drone(battle, commander))
    else:
        raise ValueError(f"Unknown RAM ability {ability_id}")

    return events


def resolve_paint_target(
    catalog: ContentCatalog,
    battle: BattleState,
    painter: UnitState,
    target: UnitState,
) -> list[DomainEvent]:
    ability = catalog.abilities.get("paint_target")
    if not ability:
        raise ValueError("Paint Target not in catalog")
    paint_range = getattr(ability, "range", None) or 12
    dist = axial_distance(painter.position, target.position)
    if dist > paint_range:
        raise ValueError("Paint target out of range")
    if not has_line_of_sight(catalog, battle, painter.position, target.position):
        raise ValueError("No line of sight to paint target")
    if target.side == painter.side or not target.alive or target.category == "decoy":
        raise ValueError("Paint requires a living opposition unit")

    events: list[DomainEvent] = []
    if battle.activation and battle.activation.actor_id == painter.unit_instance_id:
        used = battle.activation.actions.spend(ActionType.MINOR)
        events.append(
            DomainEvent(
                type="action_spent",
                actor_id=painter.unit_instance_id,
                payload={"action": used.value, "for": "paint_target"},
            )
        )

    # Clear prior paints from this painter, then apply
    marker = f"painted_by:{painter.unit_instance_id}"
    for u in battle.units.values():
        if marker in u.statuses:
            u.statuses = [s for s in u.statuses if s not in ("painted", marker)]
    if "painted" not in target.statuses:
        target.statuses.append("painted")
    if marker not in target.statuses:
        target.statuses.append(marker)
    events.append(
        DomainEvent(
            type="status_applied",
            payload={"unit_id": target.unit_instance_id, "status": "painted", "painter_id": painter.unit_instance_id},
        )
    )
    return events
