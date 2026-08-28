import os
from pathlib import Path

# Ensure content root resolves for local pytest
ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("CONTENT_ROOT", str(ROOT / "content"))

from app.application.services import run_headless_simulation
from app.content.loader import load_catalog
from app.domain.hex import Hex, axial_distance
from app.domain.rng import SeededRNG
from app.engine.formation import deploy_formation, plan_squad_move
from app.engine.objective import current_control, score_objective_at_round_end
from app.engine.battle import execute_option
from app.engine.options import build_options, fallback_select, self_destruct_hits_enemy
from app.engine.state import ActionPool, ActivationState, BattleState, ModelState, UnitState, cohesion_ok, evaluate_terminal, signal_radius
from app.domain.enums import ActionType, BattleStatus, Side


def test_content_loads():
    catalog = load_catalog(force=True)
    assert "friendly_infantry_squad" in catalog.units
    assert "rifle" in catalog.weapons
    assert "vs_middle_east_50" in catalog.maps
    assert catalog.weapons["micro_explosive"].ammo == 1


def test_hex_distance():
    assert axial_distance(Hex(0, 0), Hex(1, 0)) == 1
    assert axial_distance(Hex(0, 0), Hex(0, 1)) == 1
    assert axial_distance(Hex(0, 0), Hex(2, 0)) == 2
    # odd-r brick: row stagger — (1,0) and (0,1) are neighbors
    assert axial_distance(Hex(1, 0), Hex(0, 1)) == 1
    n0 = { (h.q, h.r) for h in Hex(5, 4).neighbors() }
    assert (6, 4) in n0 and (5, 3) in n0 and (4, 4) in n0
    assert len(n0) == 6


def test_offset_map_is_rectangular_neighbors():
    """Even/odd rows use different neighbor sets (tabletop brick)."""
    even = {(h.q, h.r) for h in Hex(10, 10).neighbors()}
    odd = {(h.q, h.r) for h in Hex(10, 11).neighbors()}
    assert (11, 10) in even
    assert (9, 9) in even  # NW for even row
    assert (11, 11) in odd  # NE for odd row
    assert even != odd


def test_seeded_rng_reproducible():
    a = SeededRNG(42)
    b = SeededRNG(42)
    assert a.roll_nd6(3) == b.roll_nd6(3)


def test_cohesion_ok():
    assert cohesion_ok([Hex(0, 0), Hex(3, 0), Hex(0, 3)], 6)
    assert not cohesion_ok([Hex(0, 0), Hex(7, 0)], 6)


def test_deploy_formation_places_ten_distinct():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    models = [ModelState(model_id=f"m{i}", hp=1, max_hp=1, position=None) for i in range(1, 11)]
    unit = UnitState(
        unit_instance_id="sq",
        definition_id="friendly_infantry_squad",
        display_name="Infantry Squad",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="blue_infantry",
        position=Hex(10, 45),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=models,
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    occ: dict[str, str] = {}
    formation = deploy_formation(catalog, battle, unit, Hex(10, 45), occ)
    assert formation is not None
    assert len(formation) == 10
    assert len(set(formation.values())) == 10
    assert cohesion_ok(list(formation.values()), 6)
    lead = unit.leader_model()
    assert lead is not None
    assert formation[lead.model_id] == Hex(10, 45)


def test_headless_simulation_completes():
    result = run_headless_simulation(seed=42, max_rounds=40)
    assert result["status"] in ("VICTORY", "DEFEAT", "DRAW", "ACTIVE")
    assert result["event_count"] > 0
    # Prefer terminal; if ACTIVE still, at least progressed
    assert result["round"] >= 1


def test_headless_deterministic():
    a = run_headless_simulation(seed=7, max_rounds=20)
    b = run_headless_simulation(seed=7, max_rounds=20)
    assert a["status"] == b["status"]
    assert a["event_count"] == b["event_count"]
    assert a["round"] == b["round"]


def _drone_at(uid: str, side: Side, hex_: Hex, definition: str, name: str) -> UnitState:
    return UnitState(
        unit_instance_id=uid,
        definition_id=definition,
        display_name=name,
        side=side,
        category="drone",
        roles=["disposable", "area_damage"],
        asset_set_id="blue_drone_1a",
        position=hex_,
        speed=10,
        attack=0,
        defense=12,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=hex_)],
        weapons=[],
        abilities=["self_destruct"],
        movement_traits=["flying"],
        size_class="small",
    )


def test_self_destruct_not_offered_in_empty_space():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(40, 48), "friendly_one_way_drone", "One-Way")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(5, 5),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(5, 5))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    assert not self_destruct_hits_enemy(catalog, battle, drone)
    opts = build_options(catalog, battle, drone)
    assert not any(o["subroutine"] == "self_destruct" for o in opts.values())


def test_self_destruct_offered_when_enemy_in_blast():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(10, 10), "friendly_one_way_drone", "One-Way")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(10, 11),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(10, 11))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    assert self_destruct_hits_enemy(catalog, battle, drone)
    opts = build_options(catalog, battle, drone)
    assert any(o["subroutine"] == "self_destruct" for o in opts.values())


def test_disposable_bomber_fallback_self_destructs_in_range():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(10, 10), "friendly_one_way_drone", "One-Way")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(10, 11),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(10, 11))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, drone)
    picked = fallback_select(opts, drone, battle)
    assert opts[picked]["subroutine"] == "self_destruct"


def test_disposable_bomber_move_preview_hunts_enemies_not_center():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(40, 48), "friendly_one_way_drone", "One-Way")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(38, 47),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(38, 47))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, drone)
    moves = [o for o in opts.values() if o["subroutine"] == "move"]
    assert moves
    picked = fallback_select(opts, drone, battle)
    assert opts[picked]["subroutine"] == "move"
    dest = opts[picked]["preview"]["affected_hexes"][0]
    center = Hex(25, 25)
    dest_hex = Hex(dest["q"], dest["r"])
    assert axial_distance(dest_hex, enemy.position) < axial_distance(dest_hex, center)


def test_self_destruct_preview_lists_friendly_fire():
    from app.engine.options import self_destruct_blast_assessment

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.OPPOSITION, Hex(10, 10), "opposition_impact_drone", "Impact")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="friendly_ranger_squad",
        display_name="Blue Ranger",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="blue_infantry",
        position=Hex(10, 11),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(10, 11))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    ally = UnitState(
        unit_instance_id="a1",
        definition_id="opposition_ranger_squad",
        display_name="Red Ranger",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(11, 10),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(11, 10))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy, ally.unit_instance_id: ally}
    battle.activation = ActivationState(activation_id="a1", actor_id=drone.unit_instance_id, actions=ActionPool())
    blast = self_destruct_blast_assessment(catalog, battle, drone)
    assert blast["friendly_fire"] is True
    assert blast["friendly_models_in_blast"] >= 1
    assert blast["enemy_models_in_blast"] >= 1
    opts = build_options(catalog, battle, drone)
    sd = next(o for o in opts.values() if o["subroutine"] == "self_destruct")
    assert sd["preview"]["friendly_fire"] is True
    assert "friendly_fire" in (sd["preview"].get("risk_tags") or [])


def test_call_support_drone_ram_resolves():
    from app.engine.combat import resolve_ram_ability

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        ram_abilities=["defense_matrix", "call_for_action", "targeting_assistance"],
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(25, 25), "commander", "friendly_commander", "CMDR")
    support = _drone_at("f8", Side.FRIENDLY, Hex(26, 25), "friendly_commander_support_drone", "Support")
    support.category = "drone"
    battle.units = {cmd.unit_instance_id: cmd, support.unit_instance_id: support}
    battle.support_drone_unit_id = support.unit_instance_id
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    opts = build_options(catalog, battle, cmd, sample_moves=0)
    assert "ram:call_support_drone" in opts
    assert opts["ram:call_support_drone"]["preview"].get("disabled") is not True
    events = resolve_ram_ability(catalog, battle, cmd, "call_support_drone")
    assert any(e.type == "support_drone_summoned" for e in events)
    assert "summoned_load" in support.statuses


def test_call_support_drone_disabled_out_of_signal():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        ram_abilities=["defense_matrix"],
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(5, 5), "commander", "friendly_commander", "CMDR")
    support = _drone_at("f8", Side.FRIENDLY, Hex(40, 40), "friendly_commander_support_drone", "Support")
    support.category = "drone"
    battle.units = {cmd.unit_instance_id: cmd, support.unit_instance_id: support}
    battle.support_drone_unit_id = support.unit_instance_id
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    opts = build_options(catalog, battle, cmd, sample_moves=0)
    assert "ram:call_support_drone" in opts
    assert opts["ram:call_support_drone"]["preview"]["disabled"] is True
    assert "out of signal" in (opts["ram:call_support_drone"]["preview"]["blocked_reason"] or "").lower()


def _token(uid: str, side: Side, hex_: Hex, category: str, definition: str, name: str) -> UnitState:
    return UnitState(
        unit_instance_id=uid,
        definition_id=definition,
        display_name=name,
        side=side,
        category=category,
        roles=["frontline"] if category == "soldier_squad" else ["command"],
        asset_set_id="blue_infantry",
        position=hex_,
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=5 if category == "commander" else 1, max_hp=5 if category == "commander" else 1, position=hex_)],
        weapons=[],
        abilities=[],
        movement_traits=["ground"],
        ram_current=6 if category == "commander" else None,
        ram_capacity=6 if category == "commander" else None,
        signal_range=12 if category == "commander" else None,
    )


def test_temple_scores_uncontested_and_not_when_contested():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        round=1,
        vp_to_win=5,
    )
    blue = _token("f1", Side.FRIENDLY, Hex(25, 25), "commander", "friendly_commander", "CMDR")
    red = _token("o1", Side.OPPOSITION, Hex(0, 0), "soldier_squad", "opposition_line_cell", "Inf")
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    assert current_control(battle) == "friendly"
    score_objective_at_round_end(battle)
    assert battle.friendly_vp == 1
    assert battle.opposition_vp == 0

    red.position = Hex(26, 25)
    red.models[0].position = Hex(26, 25)
    assert current_control(battle) == "contested"
    score_objective_at_round_end(battle)
    assert battle.friendly_vp == 1
    assert battle.opposition_vp == 0


def test_five_temple_points_wins():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        round=5,
        friendly_vp=4,
        vp_to_win=5,
    )
    blue = _token("f1", Side.FRIENDLY, Hex(25, 24), "commander", "friendly_commander", "CMDR")
    red = _token("o1", Side.OPPOSITION, Hex(0, 0), "soldier_squad", "opposition_line_cell", "Inf")
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    score_objective_at_round_end(battle)
    assert battle.friendly_vp == 5
    assert evaluate_terminal(battle) == BattleStatus.VICTORY
    assert battle.status == BattleStatus.VICTORY


def test_ram_abilities_stay_listed_when_blocked():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        ram_abilities=["targeting_assistance", "defense_matrix", "call_for_action"],
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(25, 45), "commander", "friendly_commander", "CMDR")
    battle.units = {cmd.unit_instance_id: cmd}
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    opts = list(build_options(catalog, battle, cmd, sample_moves=0).values())
    ram = [o for o in opts if o["subroutine"] == "ram_ability"]
    ids = {o["preview"]["ability_id"]: o for o in ram}
    assert "defense_matrix" in ids
    assert "targeting_assistance" in ids
    assert "call_for_action" in ids
    assert ids["targeting_assistance"]["preview"]["disabled"] is True
    assert ids["call_for_action"]["preview"]["disabled"] is True
    assert ids["defense_matrix"]["preview"].get("disabled") in (False, None)


def test_fallback_pushes_temple_instead_of_shooting_when_empty():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    # Blue infantry outside the 5-hex ring, in rifle range of red, can walk closer to (25,25)
    blue = UnitState(
        unit_instance_id="f1",
        definition_id="friendly_infantry_squad",
        display_name="Infantry",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["frontline", "mobile_damage"],
        asset_set_id="blue_infantry",
        position=Hex(25, 16),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 16))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(25, 10),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 10))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=blue.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, blue, sample_moves=5)
    chosen = opts[fallback_select(opts, blue, battle)]
    assert chosen["subroutine"] == "move"
    assert chosen["preview"]["closes_on_objective"] is True


def test_direct_attack_drone_shoots_instead_of_temple_walk():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = UnitState(
        unit_instance_id="d1",
        definition_id="friendly_direct_attack_drone",
        display_name="Direct Attack Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["mobile_damage", "area_damage"],
        asset_set_id="blue_drone_1b",
        position=Hex(25, 18),
        speed=9,
        attack=0,
        defense=11,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 18))],
        weapons=["micro_explosive"],
        abilities=[],
        movement_traits=["flying"],
        ammo={},
    )
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(25, 12),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 12))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, red.unit_instance_id: red}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, drone, sample_moves=5)
    chosen = opts[fallback_select(opts, drone, battle)]
    assert chosen["subroutine"] == "attack"


def test_empty_drone_returns_to_deploy_instead_of_pacing():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = UnitState(
        unit_instance_id="d1",
        definition_id="friendly_direct_attack_drone",
        display_name="Direct Attack Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["mobile_damage", "area_damage"],
        asset_set_id="blue_drone_1b",
        position=Hex(25, 25),
        speed=9,
        attack=0,
        defense=11,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 25))],
        weapons=["micro_explosive"],
        abilities=[],
        movement_traits=["flying"],
        ammo={"micro_explosive": 0},
    )
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(0, 0),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(0, 0))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, red.unit_instance_id: red}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, drone, sample_moves=5)
    chosen = opts[fallback_select(opts, drone, battle)]
    assert chosen["subroutine"] == "return_to_resupply" or chosen["preview"].get("closes_on_resupply") is True


def test_drone_rearms_when_it_reaches_deploy():
    catalog = load_catalog(force=True)
    from app.engine.resupply import try_resupply_at_deploy

    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        map_id="vs_middle_east_50",
    )
    drone = UnitState(
        unit_instance_id="d1",
        definition_id="friendly_direct_attack_drone",
        display_name="Direct Attack Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["mobile_damage", "area_damage"],
        asset_set_id="blue_drone_1b",
        position=Hex(25, 47),
        speed=9,
        attack=0,
        defense=11,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 47))],
        weapons=["micro_explosive"],
        abilities=[],
        movement_traits=["flying"],
        ammo={"micro_explosive": 0},
    )
    battle.units = {drone.unit_instance_id: drone}
    events = try_resupply_at_deploy(catalog, battle, drone)
    assert events
    assert drone.ammo["micro_explosive"] == 1


def test_empty_drone_resupply_option_is_a_dash():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = UnitState(
        unit_instance_id="d1",
        definition_id="friendly_direct_attack_drone",
        display_name="Direct Attack Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["mobile_damage", "area_damage"],
        asset_set_id="blue_drone_1b",
        position=Hex(25, 25),
        speed=9,
        attack=0,
        defense=11,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 25))],
        weapons=["micro_explosive"],
        abilities=[],
        movement_traits=["flying"],
        ammo={"micro_explosive": 0},
    )
    battle.units = {drone.unit_instance_id: drone}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, drone, sample_moves=5)
    rtb = next(o for o in opts.values() if o["subroutine"] == "return_to_resupply")
    assert rtb["preview"]["dash"] is True
    assert rtb["preview"]["movement_cost"] > drone.speed
    assert rtb["preview"]["movement_cost"] <= drone.speed * 2


def test_empty_drone_dash_spends_both_moves_in_one_execute():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        status=BattleStatus.ACTIVE,
    )
    drone = UnitState(
        unit_instance_id="d1",
        definition_id="friendly_direct_attack_drone",
        display_name="Direct Attack Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["mobile_damage", "area_damage"],
        asset_set_id="blue_drone_1b",
        position=Hex(25, 25),
        speed=9,
        attack=0,
        defense=11,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 25))],
        weapons=["micro_explosive"],
        abilities=[],
        movement_traits=["flying"],
        ammo={"micro_explosive": 0},
    )
    battle.units = {drone.unit_instance_id: drone}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(),
    )
    opts = build_options(catalog, battle, drone, sample_moves=5)
    battle.activation.options = opts
    rtb_id = next(oid for oid, o in opts.items() if o["subroutine"] == "return_to_resupply")
    start = drone.position
    execute_option(battle, rtb_id)
    assert axial_distance(start, drone.position) > drone.speed
    assert not battle.activation.actions.can_spend(ActionType.MOVE)


def test_infantry_dash_completes_in_one_agent_call():
    from app.agents.orchestration import run_agent_activation
    from app.config import settings

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        status=BattleStatus.ACTIVE,
        round=1,
    )
    inf = UnitState(
        unit_instance_id="f1",
        definition_id="friendly_infantry_squad",
        display_name="Infantry Squad",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="blue_infantry",
        position=Hex(10, 40),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(10, 40))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(0, 0),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(0, 0))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {inf.unit_instance_id: inf, red.unit_instance_id: red}
    battle.initiative = [inf.unit_instance_id, red.unit_instance_id]
    battle.initiative_index = 0
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=inf.unit_instance_id,
        actions=ActionPool(),
    )
    start = inf.position
    old = settings.llm_external_enabled
    settings.llm_external_enabled = False
    try:
        run_agent_activation(battle, db=None)
    finally:
        settings.llm_external_enabled = old
    assert axial_distance(start, inf.position) > inf.speed
    moved = [e for e in battle.events if e.get("type") == "unit_moved"]
    assert len(moved) == 1
    assert len(moved[0]["payload"]["path"]) > inf.speed


def test_ram_ability_option_ids_are_stable():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        ram_abilities=["defense_matrix", "call_for_action"],
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(25, 25), "commander", "friendly_commander", "CMDR")
    inf = _token("f2", Side.FRIENDLY, Hex(26, 25), "soldier_squad", "friendly_infantry_squad", "Inf")
    battle.units = {cmd.unit_instance_id: cmd, inf.unit_instance_id: inf}
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    opts1 = build_options(catalog, battle, cmd, sample_moves=0)
    opts2 = build_options(catalog, battle, cmd, sample_moves=0)
    assert "ram:call_for_action" in opts1
    assert opts1["ram:call_for_action"]["option_id"] == opts2["ram:call_for_action"]["option_id"]


def test_call_for_action_works_after_commander_moves():
    from app.engine.options import make_move_option

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        ram_abilities=["call_for_action"],
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(20, 20), "commander", "friendly_commander", "CMDR")
    cmd.speed = 6
    inf = _token("f2", Side.FRIENDLY, Hex(26, 25), "soldier_squad", "friendly_infantry_squad", "Inf")
    battle.units = {cmd.unit_instance_id: cmd, inf.unit_instance_id: inf}
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    move_opt = make_move_option(catalog, battle, cmd, 24, 22)
    battle.activation.options[move_opt["option_id"]] = move_opt
    execute_option(battle, move_opt["option_id"])
    base_speed = inf.speed
    execute_option(battle, "ram:call_for_action")
    assert cmd.ram_current == 3
    assert "call_for_action" in inf.statuses
    assert inf.speed == base_speed + 2


def test_ram_cast_with_stale_persisted_options():
    """GET snapshot rebuilds stable ram:* ids; execute must not fail on stale DB option keys."""
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
        ram_abilities=["call_for_action"],
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(20, 20), "commander", "friendly_commander", "CMDR")
    inf = _token("f2", Side.FRIENDLY, Hex(21, 20), "soldier_squad", "friendly_infantry_squad", "Inf")
    battle.units = {cmd.unit_instance_id: cmd, inf.unit_instance_id: inf}
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    battle.activation.options = {"dead-beef-uuid": {"option_id": "dead-beef-uuid", "subroutine": "hold"}}
    execute_option(battle, "ram:call_for_action")
    assert cmd.ram_current == 3
    assert "call_for_action" in inf.statuses


def test_attack_ids_stable_and_stale_uuid_still_fires():
    """Attacks must not rebuild UUID menus mid-execute (that made every AI unit Hold)."""
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    cmd = _token("f1", Side.FRIENDLY, Hex(20, 20), "commander", "friendly_commander", "CMDR")
    cmd.weapons = ["commander_sniper"]
    cmd.attack = 8
    enemy = _token("o1", Side.OPPOSITION, Hex(21, 20), "soldier_squad", "opposition_line_cell", "Inf")
    battle.units = {cmd.unit_instance_id: cmd, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(activation_id="a1", actor_id=cmd.unit_instance_id, actions=ActionPool())
    opts1 = build_options(catalog, battle, cmd, sample_moves=0)
    opts2 = build_options(catalog, battle, cmd, sample_moves=0)
    attack_id = "attack:commander_sniper:o1"
    assert attack_id in opts1
    assert opts1[attack_id]["option_id"] == opts2[attack_id]["option_id"]

    battle.activation.options = {
        "stale-uuid": {
            "option_id": "stale-uuid",
            "subroutine": "attack",
            "preview": {
                "weapon_id": "commander_sniper",
                "target_unit_id": "o1",
                "target_model_id": "m1",
            },
        }
    }
    execute_option(battle, "stale-uuid")
    assert any(e.get("type") == "weapon_fired" for e in battle.events)


def test_squad_grenade_is_one_throw_not_a_volley():
    from app.engine.combat import resolve_attack

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    blue_models = [ModelState(model_id=f"m{i}", hp=1, max_hp=1, position=Hex(20, 20 + (i % 3))) for i in range(1, 11)]
    red_models = [ModelState(model_id=f"m{i}", hp=1, max_hp=1, position=Hex(21, 20 + (i % 3))) for i in range(1, 11)]
    blue = UnitState(
        unit_instance_id="f2",
        definition_id="friendly_infantry_squad",
        display_name="Inf",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["frontline", "mobile_damage"],
        asset_set_id="blue_infantry",
        position=Hex(20, 20),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=blue_models,
        weapons=["rifle", "squad_grenade"],
        abilities=[],
        movement_traits=["ground"],
        ammo={"squad_grenade": 1},
    )
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Inf",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(21, 20),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=red_models,
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    battle.activation = ActivationState(activation_id="a1", actor_id=blue.unit_instance_id, actions=ActionPool())
    events = resolve_attack(catalog, battle, blue, "squad_grenade", red)
    fired = next(e for e in events if e.type == "weapon_fired")
    assert fired.payload["attack_count"] == 1
    assert len(fired.payload["shots"]) == 1
    assert blue.ammo["squad_grenade"] == 0


def test_aiming_reposition_is_not_a_free_move():
    """Attack may shuffle models ≤ AIM_REPOSITION_BUDGET hexes — not a full Speed advance."""
    from app.engine.combat import resolve_attack
    from app.engine.formation import AIM_REPOSITION_BUDGET, plan_firing_repositions, squad_can_engage_target

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    # Rifle range 10; place attacker 16 hexes away so old budget=speed(6) could close, new cannot.
    red_anchor = Hex(20, 20)
    blue_anchor = Hex(20, 36)
    assert axial_distance(red_anchor, blue_anchor) == 16
    red_models = [
        ModelState(model_id=f"m{i}", hp=1, max_hp=1, position=Hex(20 + (i % 3) - 1, 20 + (i // 3)))
        for i in range(1, 11)
    ]
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Inf",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=red_anchor,
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=red_models,
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    blue = _token("f1", Side.FRIENDLY, blue_anchor, "commander", "friendly_commander", "CMDR")
    battle.units = {red.unit_instance_id: red, blue.unit_instance_id: blue}
    battle.activation = ActivationState(activation_id="a1", actor_id=red.unit_instance_id, actions=ActionPool())

    weapon_range = catalog.weapons["rifle"].range
    assert not squad_can_engage_target(catalog, battle, red, blue, weapon_range)
    assert plan_firing_repositions(catalog, battle, red, [blue_anchor], weapon_range) == []

    try:
        resolve_attack(catalog, battle, red, "rifle", blue)
        assert False, "expected out-of-range attack to fail"
    except ValueError as exc:
        assert "range" in str(exc).lower() or "line of sight" in str(exc).lower()

    # Still out of rifle range after a 2-hex shuffle: must move (spend Move) to close.
    assert axial_distance(red.position, blue.position) > weapon_range + AIM_REPOSITION_BUDGET


def test_aiming_reposition_paths_cap_at_budget():
    from app.engine.formation import AIM_REPOSITION_BUDGET, plan_firing_repositions

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    # Just outside rifle range so a short aim step can help rear models, but not a dash.
    red_anchor = Hex(20, 20)
    blue_anchor = Hex(20, 31)  # distance 11; rifle 10 → need ≤2 to engage
    red_models = [
        ModelState(model_id=f"m{i}", hp=1, max_hp=1, position=Hex(20 + (i % 3) - 1, 20 + (i // 3)))
        for i in range(1, 11)
    ]
    red = UnitState(
        unit_instance_id="o1",
        definition_id="opposition_line_cell",
        display_name="Inf",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=red_anchor,
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=red_models,
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {red.unit_instance_id: red}
    plans = plan_firing_repositions(catalog, battle, red, [blue_anchor], catalog.weapons["rifle"].range)
    for plan in plans:
        assert len(plan.path) - 1 <= AIM_REPOSITION_BUDGET


def test_spent_ram_does_not_shrink_signal_radius():
    cmd = _token("f1", Side.FRIENDLY, Hex(25, 25), "commander", "friendly_commander", "CMDR")
    assert signal_radius(cmd) == 12
    cmd.ram_current = 0
    assert signal_radius(cmd) == 12


def test_start_round_refreshes_ram_pool():
    from app.engine.battle import start_round

    cmd = _token("f1", Side.FRIENDLY, Hex(25, 25), "commander", "friendly_commander", "CMDR")
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version="v",
        width=50,
        height=50,
        round=1,
    )
    cmd.ram_current = 1
    battle.units = {cmd.unit_instance_id: cmd}
    start_round(battle)
    assert cmd.ram_current == cmd.ram_capacity
    assert any(e.get("payload", {}).get("reason") == "round_refresh" for e in battle.events)


def test_double_move_blocks_attack():
    """Move + Move burns Standard — Fire must not remain legal."""
    from app.application.services import _deserialize_battle, _serialize_battle
    from app.engine.battle import execute_option
    from app.engine.options import build_options, make_move_option

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    blue = _token("f1", Side.FRIENDLY, Hex(25, 30), "commander", "friendly_commander", "CMDR")
    red = _token("o1", Side.OPPOSITION, Hex(10, 10), "soldier_squad", "opposition_line_cell", "Inf")
    blue.weapons = ["rifle"]
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    battle.activation = ActivationState(activation_id="a1", actor_id=blue.unit_instance_id, actions=ActionPool())

    opt = make_move_option(catalog, battle, blue, 25, 29)
    battle.activation.options = {opt["option_id"]: opt}
    execute_option(battle, opt["option_id"])
    assert battle.activation.actions.moves_spent == 1
    assert battle.activation.actions.standard == 1

    # Round-trip like Docker request boundaries
    battle = _deserialize_battle(_serialize_battle(battle))
    blue = battle.units["f1"]

    opt2 = make_move_option(catalog, battle, blue, 25, 28)
    battle.activation.options[opt2["option_id"]] = opt2
    execute_option(battle, opt2["option_id"])
    assert battle.activation.actions.moves_spent == 2
    assert battle.activation.actions.standard == 0
    assert not battle.activation.actions.can_spend(ActionType.STANDARD)

    opts = build_options(catalog, battle, blue, sample_moves=0)
    assert not any(o["subroutine"] == "attack" for o in opts.values())


def test_move_then_attack_still_legal():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    blue = _token("f1", Side.FRIENDLY, Hex(25, 30), "commander", "friendly_commander", "CMDR")
    red = _token("o1", Side.OPPOSITION, Hex(25, 29), "soldier_squad", "opposition_line_cell", "Inf")
    blue.weapons = ["rifle"]
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    battle.activation = ActivationState(activation_id="a1", actor_id=blue.unit_instance_id, actions=ActionPool())

    from app.engine.battle import execute_option
    from app.engine.options import build_options, make_move_option

    opt = make_move_option(catalog, battle, blue, 26, 30)
    battle.activation.options = {opt["option_id"]: opt}
    execute_option(battle, opt["option_id"])
    assert battle.activation.actions.can_spend(ActionType.STANDARD)
    opts = build_options(catalog, battle, blue, sample_moves=0)
    assert any(o["subroutine"] == "attack" for o in opts.values())



def test_four_corners_scores_each_zone():
    from app.engine.scenarios import zone_layout
    from app.engine.objective import zone_control

    battle = BattleState(battle_id="t", session_id="s", seed=1, content_version="v", width=50, height=50, round=1)
    battle.scenario_id = "four_corners"
    battle.objective_zones = zone_layout("four_corners", 50, 50)
    zones = battle.objective_zones
    blue = _token("f1", Side.FRIENDLY, Hex(zones[0]["q"], zones[0]["r"]), "commander", "friendly_commander", "CMDR")
    red = _token("o1", Side.OPPOSITION, Hex(zones[1]["q"], zones[1]["r"]), "soldier_squad", "opposition_line_cell", "Inf")
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    assert zone_control(battle, zones[0]) == "friendly"
    assert zone_control(battle, zones[1]) == "opposition"
    score_objective_at_round_end(battle)
    assert battle.friendly_vp == 1
    assert battle.opposition_vp == 1


def test_capture_flags_grab_and_score():
    from app.engine.battle import create_battle
    from app.engine.objective import grab_flag_options, resolve_grab_flag, score_objective_at_round_end
    from app.engine.scenarios import zone_layout

    catalog = load_catalog(force=True)
    prep = {
        "mission_id": "freestyle_vs_15",
        "map_id": "vs_middle_east_50",
        "point_cap": 15,
        "scenario_id": "capture_the_flags",
        "avatar": "male",
        "ram_abilities": ["targeting_assistance", "defense_matrix", "call_for_action"],
        "army": [{"definition_id": "friendly_infantry_squad", "count": 1}],
    }
    battle = create_battle("s1", prep, seed=42)
    assert len(battle.flags) == 3
    infantry = next(u for u in battle.units.values() if u.definition_id == "friendly_infantry_squad")
    center = next(z for z in battle.objective_zones if z["id"] == "center")
    leader = infantry.leader_model()
    assert leader
    leader.position = Hex(center["q"], center["r"])
    infantry.sync_position_from_leader()
    flags = grab_flag_options(battle, infantry)
    assert flags
    resolve_grab_flag(battle, infantry, flags[0]["flag_id"])
    battle.round = 1
    score_objective_at_round_end(battle)
    assert battle.friendly_vp == 1
    assert battle.opposition_vp == 0


def test_opposition_impact_drone_self_destruct_is_aoe1():
    catalog = load_catalog(force=True)
    unit = catalog.units["opposition_impact_drone"]
    assert "self_destruct" in unit.abilities
    assert "self_destruct_aoe2" not in unit.abilities
    assert catalog.abilities["self_destruct"].area == 1


def test_anti_armor_drone_uses_heavy_cannon_twelve():
    catalog = load_catalog(force=True)
    assert catalog.weapons["heavy_cannon_12"].damage == 12
    assert catalog.weapons["heavy_cannon_12"].range == 10
    assert catalog.weapons["heavy_cannon_12"].ammo is None
    assert catalog.units["friendly_anti_armor_drone"].weapons == ["heavy_cannon_12"]


def test_only_direct_attack_drone_rtb_when_empty():
    """Deploy reload is exclusive to Blue Direct Attack Drone."""
    from app.engine.resupply import should_return_to_resupply

    catalog = load_catalog(force=True)
    direct = UnitState(
        unit_instance_id="d1",
        definition_id="friendly_direct_attack_drone",
        display_name="Direct Attack Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["mobile_damage"],
        asset_set_id="blue_drone_1b",
        position=Hex(25, 25),
        speed=9,
        attack=0,
        defense=11,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 25))],
        weapons=["micro_explosive"],
        abilities=[],
        movement_traits=["flying"],
        ammo={"micro_explosive": 0},
    )
    anti_armor = UnitState(
        unit_instance_id="aa1",
        definition_id="friendly_anti_armor_drone",
        display_name="Anti-Armor Drone",
        side=Side.FRIENDLY,
        category="drone",
        roles=["anti_armor"],
        asset_set_id="friendly_anti_armor_drone",
        position=Hex(25, 25),
        speed=6,
        attack=0,
        defense=8,
        armor=20,
        models=[ModelState(model_id="m1", hp=10, max_hp=10, position=Hex(25, 25))],
        weapons=["heavy_cannon_12"],
        abilities=[],
        movement_traits=["ground"],
        ammo={},
    )
    assert should_return_to_resupply(catalog, direct) is True
    assert should_return_to_resupply(catalog, anti_armor) is False


def test_disposable_bomber_can_dash_and_chain_second_move():
    from app.engine.options import agent_move_budget, should_chain_dash

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(40, 48), "friendly_one_way_drone", "One-Way")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(25, 20),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(25, 20))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    assert agent_move_budget(catalog, battle, drone) == drone.speed * 2
    opts = build_options(catalog, battle, drone)
    battle.activation.options = opts
    assert should_chain_dash(catalog, battle, drone, "move") is True
    # After a normal Move spend, still chain a second Move toward the foe
    battle.activation.actions.spend(ActionType.MOVE)
    battle.activation.options = build_options(catalog, battle, drone)
    assert should_chain_dash(catalog, battle, drone, "move") is True
    # Once Self-destruct is legal, stop dashing
    drone.position = Hex(25, 20)
    drone.models[0].position = Hex(25, 20)
    battle.activation.options = build_options(catalog, battle, drone)
    assert any(o["subroutine"] == "self_destruct" for o in battle.activation.options.values())
    assert should_chain_dash(catalog, battle, drone, "move") is False


def test_disposable_bomber_blast_hexes_not_buried_by_distant_infantry():
    """Regression: troop_pull to far squads used to outscore (~thousands) blast hexes (~600)."""
    from app.engine.options import fallback_select

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(20, 20), "friendly_one_way_drone", "One-Way")
    drone.speed = 20
    near_dog = UnitState(
        unit_instance_id="dog1",
        definition_id="opposition_impact_drone",
        display_name="Impact",
        side=Side.OPPOSITION,
        category="drone",
        roles=["disposable", "area_damage"],
        asset_set_id="red_drone_1a",
        position=Hex(22, 20),
        speed=20,
        attack=0,
        defense=12,
        armor=8,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(22, 20))],
        weapons=[],
        abilities=["self_destruct"],
        movement_traits=["flying"],
    )
    # Fat infantry blob far away — old scoring chased this instead of detonating on the dog
    far_squad = UnitState(
        unit_instance_id="inf1",
        definition_id="opposition_infantry_squad",
        display_name="Infantry",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(5, 5),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[
            ModelState(model_id=f"m{i}", hp=1, max_hp=1, position=Hex(5, 5)) for i in range(10)
        ],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {
        drone.unit_instance_id: drone,
        near_dog.unit_instance_id: near_dog,
        far_squad.unit_instance_id: far_squad,
    }
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    opts = build_options(catalog, battle, drone)
    battle.activation.options = opts
    move_opts = [o for o in opts.values() if o["subroutine"] == "move"]
    assert move_opts, "expected move options toward the dog"
    assert all(
        (o.get("preview") or {}).get("detonation_would_hit") for o in move_opts
    ), "when a blast hex is reachable, only detonation landings should be offered"
    pick = fallback_select(opts, drone, battle)
    assert (opts[pick].get("preview") or {}).get("detonation_would_hit")


def test_self_destruct_still_offered_after_dash():
    """Regression: SD is Minor, but was gated behind Standard — dash (moves_spent=2) hid it."""
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(20, 20), "friendly_one_way_drone", "One-Way")
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(21, 20),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(21, 20))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    # Simulate a full dash: Move pool + Standard-as-move
    battle.activation.actions.spend(ActionType.MOVE)
    battle.activation.actions.spend(ActionType.MOVE)
    assert battle.activation.actions.moves_spent == 2
    assert battle.activation.actions.can_spend(ActionType.STANDARD) is False
    assert battle.activation.actions.can_spend(ActionType.MINOR) is True

    opts = build_options(catalog, battle, drone)
    assert any(o["subroutine"] == "self_destruct" for o in opts.values()), (
        "after dash onto a blast hex, Self-destruct (Minor) must still be offered"
    )


def test_ram_boosted_bomber_move_budget_is_triple_speed():
    from app.engine.options import agent_move_budget, remaining_move_spends, should_chain_dash

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    drone = _drone_at("d1", Side.FRIENDLY, Hex(40, 48), "friendly_one_way_drone", "One-Way")
    drone.speed = 10
    drone.size_class = "small"
    enemy = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(10, 10),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(10, 10))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {drone.unit_instance_id: drone, enemy.unit_instance_id: enemy}
    # 1 RAM → ActionPool standard=2, move=1 → three Move spends
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=drone.unit_instance_id,
        actions=ActionPool(standard=2, move=1, minor=1),
    )
    assert remaining_move_spends(battle.activation.actions) == 3
    assert agent_move_budget(catalog, battle, drone) == 30
    battle.activation.options = build_options(catalog, battle, drone)
    assert should_chain_dash(catalog, battle, drone, "move") is True
    # After a normal double-move (moves_spent=2) with one Standard left, still chain
    battle.activation.actions.spend(ActionType.MOVE)
    battle.activation.actions.spend(ActionType.MOVE)
    assert battle.activation.actions.moves_spent == 2
    assert battle.activation.actions.standard == 1
    battle.activation.options = build_options(catalog, battle, drone)
    assert should_chain_dash(catalog, battle, drone, "move") is True


def test_paint_target_order_makes_rangers_paint():
    from app.engine.options import fallback_select

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    ranger = UnitState(
        unit_instance_id="r1",
        definition_id="friendly_ranger_squad",
        display_name="Rangers",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["recon", "mobile_damage"],
        asset_set_id="friendly_ranger_squad",
        position=Hex(20, 20),
        speed=8,
        attack=0,
        defense=11,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(20, 20))],
        weapons=["rifle"],
        abilities=["drop_smoke", "paint_target"],
        movement_traits=["ground"],
        size_class="medium",
    )
    foe = UnitState(
        unit_instance_id="e1",
        definition_id="opposition_line_cell",
        display_name="Infantryman",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=Hex(22, 20),
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=Hex(22, 20))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle.units = {ranger.unit_instance_id: ranger, foe.unit_instance_id: foe}
    battle.directives = [
        {
            "active": True,
            "scope": "global",
            "order_id": "paint_target",
            "raw_text": f"Paint {foe.display_name} for Airstrike.",
            "derived_tags": ["paint_target", "focus_fire"],
            "target_refs": [{"kind": "unit", "unit_instance_id": foe.unit_instance_id}],
        }
    ]
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=ranger.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    opts = build_options(catalog, battle, ranger)
    pick = fallback_select(opts, ranger, battle)
    assert opts[pick]["subroutine"] == "paint_target"
    assert (opts[pick].get("preview") or {}).get("target_unit_id") == foe.unit_instance_id


def test_opposition_commander_deployed_with_stats():
    from app.engine.battle import create_battle

    catalog = load_catalog(force=True)
    prep = {
        "mission_id": "freestyle_vs_15",
        "map_id": "vs_middle_east_50",
        "point_cap": 15,
        "avatar": "male",
        "ram_abilities": ["targeting_assistance", "defense_matrix", "call_for_action"],
        "army": [{"definition_id": "friendly_infantry_squad", "count": 1}],
    }
    battle = create_battle("s-opp-cmd", prep, seed=42)
    red_cmd = next(
        (u for u in battle.units.values() if u.definition_id == "opposition_commander"),
        None,
    )
    assert red_cmd is not None
    assert red_cmd.alive
    assert red_cmd.speed == 6
    assert red_cmd.defense == 8
    assert red_cmd.armor == 20
    assert red_cmd.ram_capacity == 6
    assert red_cmd.signal_range == 12
    assert red_cmd.weapons == ["heavy_cannon"]
    assert catalog.weapons["heavy_cannon"].damage == 10
    assert catalog.weapons["heavy_cannon"].range == 10
    assert battle.opposition_ram_abilities == ["targeting_assistance", "call_for_action", "defense_matrix"]


def test_killing_opposition_commander_is_victory():
    from app.engine.state import evaluate_terminal

    battle = BattleState(
        battle_id="b1",
        session_id="s1",
        seed=1,
        content_version="test",
        width=50,
        height=50,
    )
    blue = _token("f1", Side.FRIENDLY, Hex(25, 25), "commander", "friendly_commander", "CMDR")
    red = _token("o1", Side.OPPOSITION, Hex(10, 10), "commander", "opposition_commander", "RED")
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    assert evaluate_terminal(battle) is None
    red.alive = False
    for m in red.models:
        m.alive = False
    assert evaluate_terminal(battle) == BattleStatus.VICTORY


def test_opposition_drone_requires_commander_signal():
    from app.engine.state import in_signal

    battle = BattleState(
        battle_id="b2",
        session_id="s1",
        seed=1,
        content_version="test",
        width=50,
        height=50,
    )
    red_cmd = _token("o1", Side.OPPOSITION, Hex(10, 10), "commander", "opposition_commander", "RED")
    red_cmd.ram_capacity = 6
    red_cmd.signal_range = 12
    dog = _drone_at("o2", Side.OPPOSITION, Hex(30, 30), "opposition_burst_drone", "Dog")
    battle.units = {red_cmd.unit_instance_id: red_cmd, dog.unit_instance_id: dog}
    assert not in_signal(battle, dog)
    dog.position = Hex(11, 10)
    for m in dog.models:
        m.position = Hex(11, 10)
    assert in_signal(battle, dog)


def test_start_round_refreshes_both_commander_ram():
    from app.engine.battle import create_battle, start_round

    prep = {
        "mission_id": "freestyle_vs_15",
        "map_id": "vs_middle_east_50",
        "point_cap": 15,
        "avatar": "male",
        "ram_abilities": ["targeting_assistance", "defense_matrix", "call_for_action"],
        "army": [{"definition_id": "friendly_infantry_squad", "count": 1}],
    }
    battle = create_battle("s-ram", prep, seed=7)
    blue = next(u for u in battle.units.values() if u.definition_id == "friendly_commander")
    red = next(u for u in battle.units.values() if u.definition_id == "opposition_commander")
    blue.ram_current = 1
    red.ram_current = 2
    start_round(battle)
    assert blue.ram_current == blue.ram_capacity
    assert red.ram_current == red.ram_capacity


def test_opposition_commander_fallback_prefers_cannon_fire():
    from app.agents.opposition_commander import commander_fallback_select
    from app.engine.options import build_options

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="b-fire",
        session_id="s1",
        seed=1,
        content_version="test",
        width=50,
        height=50,
        opposition_ram_abilities=["targeting_assistance", "defense_matrix", "call_for_action"],
    )
    red = _token("o1", Side.OPPOSITION, Hex(20, 20), "commander", "opposition_commander", "RED")
    red.weapons = ["heavy_cannon"]
    red.ram_current = 6
    red.ram_capacity = 6
    red.signal_range = 12
    blue = _token("f1", Side.FRIENDLY, Hex(22, 20), "soldier_squad", "friendly_infantry_squad", "Blue Inf")
    battle.units = {red.unit_instance_id: red, blue.unit_instance_id: blue}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=red.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    opts = build_options(catalog, battle, red)
    pick = commander_fallback_select(opts, battle, red)
    assert opts[pick]["subroutine"] == "attack"
    assert (opts[pick].get("preview") or {}).get("weapon_id") == "heavy_cannon"


def test_opposition_commander_does_not_dash_after_first_move():
    from app.agents.opposition_commander import commander_fallback_select
    from app.engine.options import build_options

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="b-nodash",
        session_id="s1",
        seed=1,
        content_version="test",
        width=50,
        height=50,
        opposition_ram_abilities=["targeting_assistance", "defense_matrix", "call_for_action"],
    )
    red = _token("o1", Side.OPPOSITION, Hex(20, 8), "commander", "opposition_commander", "RED")
    red.weapons = ["heavy_cannon"]
    red.ram_current = 6
    red.ram_capacity = 6
    red.signal_range = 12
    tank = _drone_at("o2", Side.OPPOSITION, Hex(20, 12), "opposition_tank", "Tank")
    # Enemy far south — out of cannon range so Fire is not offered
    blue = _token("f1", Side.FRIENDLY, Hex(20, 40), "soldier_squad", "friendly_infantry_squad", "Blue Inf")
    battle.units = {red.unit_instance_id: red, tank.unit_instance_id: tank, blue.unit_instance_id: blue}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=red.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    # Simulate already spent the first Move
    battle.activation.actions.spend(ActionType.MOVE)
    opts = build_options(catalog, battle, red)
    pick = commander_fallback_select(opts, battle, red)
    assert opts[pick]["subroutine"] != "move", "must not dash after first Move"
    assert opts[pick]["subroutine"] in ("hold", "ram_ability")


def test_opposition_commander_rejoins_signal_when_leash_breaks():
    """Parked at deploy while tanks push south must Move, not Hold."""
    from app.agents.opposition_commander import commander_fallback_select
    from app.engine.options import build_options
    from app.domain.hex import axial_distance

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="b-leash",
        session_id="s1",
        seed=1,
        content_version="test",
        width=50,
        height=50,
        opposition_ram_abilities=["targeting_assistance", "defense_matrix", "call_for_action"],
    )
    red = _token("o1", Side.OPPOSITION, Hex(20, 2), "commander", "opposition_commander", "RED")
    red.weapons = ["heavy_cannon"]
    red.ram_current = 6
    red.ram_capacity = 6
    red.signal_range = 12
    red.models[0].hp = 10
    red.models[0].max_hp = 10
    tank = _drone_at("o2", Side.OPPOSITION, Hex(20, 18), "opposition_tank", "Tank")
    blue = _token("f1", Side.FRIENDLY, Hex(20, 40), "soldier_squad", "friendly_infantry_squad", "Blue Inf")
    battle.units = {red.unit_instance_id: red, tank.unit_instance_id: tank, blue.unit_instance_id: blue}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=red.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    assert axial_distance(red.position, tank.position) > 12
    opts = build_options(catalog, battle, red)
    pick = commander_fallback_select(opts, battle, red)
    assert opts[pick]["subroutine"] == "move"
    dest = (opts[pick].get("preview") or {}).get("affected_hexes") or []
    assert dest
    assert axial_distance(Hex(dest[0]["q"], dest[0]["r"]), tank.position) < axial_distance(
        red.position, tank.position
    )


def test_opposition_commander_advances_when_allies_engaged():
    """When tanks are in a fight and cannon cannot reach, advance to support."""
    from app.agents.opposition_commander import commander_fallback_select
    from app.engine.options import build_options
    from app.domain.hex import axial_distance

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="b-support",
        session_id="s1",
        seed=1,
        content_version="test",
        width=50,
        height=50,
        opposition_ram_abilities=["targeting_assistance", "defense_matrix", "call_for_action"],
    )
    red = _token("o1", Side.OPPOSITION, Hex(20, 6), "commander", "opposition_commander", "RED")
    red.weapons = ["heavy_cannon"]
    red.ram_current = 6
    red.ram_capacity = 6
    red.signal_range = 12
    red.models[0].hp = 10
    red.models[0].max_hp = 10
    tank = _drone_at("o2", Side.OPPOSITION, Hex(20, 16), "opposition_tank", "Tank")
    # Engaged with the tank, but outside Red cannon range from r=6 (dist ~14)
    blue = _token("f1", Side.FRIENDLY, Hex(20, 20), "soldier_squad", "friendly_infantry_squad", "Blue Inf")
    battle.units = {red.unit_instance_id: red, tank.unit_instance_id: tank, blue.unit_instance_id: blue}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=red.unit_instance_id,
        actions=ActionPool(standard=1, move=1, minor=1),
    )
    assert axial_distance(red.position, blue.position) > 10
    assert axial_distance(tank.position, blue.position) <= 12
    opts = build_options(catalog, battle, red)
    assert not any(o.get("subroutine") == "attack" for o in opts.values())
    pick = commander_fallback_select(opts, battle, red)
    assert opts[pick]["subroutine"] == "move"
    dest = (opts[pick].get("preview") or {}).get("affected_hexes") or []
    assert dest
    assert dest[0]["r"] > red.position.r

