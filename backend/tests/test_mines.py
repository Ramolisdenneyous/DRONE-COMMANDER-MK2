"""Combat Engineer Deploy Mine / Detect Mine."""

from app.content.loader import load_catalog
from app.domain.enums import ActionType, Side
from app.domain.hex import Hex, axial_distance
from app.engine.battle import execute_option
from app.engine.mines import (
    adjacent_deploy_hexes,
    check_unit_triggers_mines,
    mines_for_snapshot,
    refresh_detect_mines,
    resolve_deploy_mine,
)
from app.engine.options import build_options
from app.engine.state import ActionPool, ActivationState, BattleState, ModelState, UnitState


def _eng(uid: str, side: Side, hex_: Hex, definition: str) -> UnitState:
    return UnitState(
        unit_instance_id=uid,
        definition_id=definition,
        display_name="Engineers",
        side=side,
        category="soldier_squad",
        roles=["support", "anti_armor"],
        asset_set_id="friendly_combat_engineers" if side == Side.FRIENDLY else "opposition_combat_engineers",
        position=hex_,
        speed=5,
        attack=0,
        defense=8,
        armor=13,
        models=[
            ModelState(model_id="m1", hp=5, max_hp=5, position=hex_),
            ModelState(model_id="m2", hp=5, max_hp=5, position=Hex(hex_.q - 1, hex_.r)),
            ModelState(model_id="m3", hp=5, max_hp=5, position=Hex(hex_.q, hex_.r - 1)),
        ],
        weapons=["shotgun"],
        abilities=["detect_mine", "deploy_mine"],
        movement_traits=["ground"],
    )


def _enemy(uid: str, hex_: Hex) -> UnitState:
    return UnitState(
        unit_instance_id=uid,
        definition_id="opposition_line_cell",
        display_name="Inf",
        side=Side.OPPOSITION,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="red_infantry",
        position=hex_,
        speed=6,
        attack=0,
        defense=10,
        armor=10,
        models=[ModelState(model_id="m1", hp=1, max_hp=1, position=hex_)],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )


def test_deploy_mine_adjacent_including_enemy_hex():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(20, 20), "friendly_combat_engineers")
    foe = _enemy("o1", Hex(21, 20))
    assert axial_distance(eng.position, foe.position) == 1
    battle.units = {eng.unit_instance_id: eng, foe.unit_instance_id: foe}
    battle.activation = ActivationState(activation_id="a1", actor_id=eng.unit_instance_id, actions=ActionPool())
    legal = adjacent_deploy_hexes(battle, eng)
    assert any(h.q == foe.position.q and h.r == foe.position.r for h in legal)
    events = resolve_deploy_mine(catalog, battle, eng, foe.position)
    assert any(e.type == "mine_deployed" for e in events)
    # Planting under an enemy detonates immediately on the planter's turn.
    assert any(e.type == "mine_triggered" for e in events)
    assert battle.mines == []
    assert battle.activation.actions.standard == 0


def test_mine_hidden_until_detect_or_trigger():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=2,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(10, 10), "friendly_combat_engineers")
    battle.units = {eng.unit_instance_id: eng}
    battle.activation = ActivationState(activation_id="a1", actor_id=eng.unit_instance_id, actions=ActionPool())
    dest = Hex(11, 10)
    resolve_deploy_mine(catalog, battle, eng, dest)
    snap = mines_for_snapshot(battle, Side.FRIENDLY)
    assert len(snap) == 1
    assert snap[0]["hidden_from_enemy"] is True
    # Enemy viewer cannot see unrevealed friendly mine
    assert mines_for_snapshot(battle, Side.OPPOSITION) == []


def test_detect_mine_passive_five_hexes():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=3,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    blue = _eng("f9", Side.FRIENDLY, Hex(20, 20), "friendly_combat_engineers")
    red = _eng("o9", Side.OPPOSITION, Hex(24, 20), "opposition_combat_engineers")
    battle.units = {blue.unit_instance_id: blue, red.unit_instance_id: red}
    battle.activation = ActivationState(activation_id="a1", actor_id=red.unit_instance_id, actions=ActionPool())
    plant = Hex(25, 20)
    assert plant in adjacent_deploy_hexes(battle, red)
    resolve_deploy_mine(catalog, battle, red, plant)
    # Deploy refreshes Detect Mine — blue engineer within 5 already reveals it.
    assert battle.mines[0].revealed is True
    assert any(m["mine_id"] == battle.mines[0].mine_id for m in mines_for_snapshot(battle, Side.FRIENDLY))


def test_detect_mine_passive_reveals_when_engineer_enters_range():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=33,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    red = _eng("o9", Side.OPPOSITION, Hex(10, 10), "opposition_combat_engineers")
    battle.units = {red.unit_instance_id: red}
    battle.activation = ActivationState(activation_id="a1", actor_id=red.unit_instance_id, actions=ActionPool())
    plant = Hex(11, 10)
    resolve_deploy_mine(catalog, battle, red, plant)
    assert battle.mines[0].revealed is False
    blue = _eng("f9", Side.FRIENDLY, Hex(14, 10), "friendly_combat_engineers")
    battle.units[blue.unit_instance_id] = blue
    events = refresh_detect_mines(catalog, battle)
    assert any(e.type == "mine_revealed" for e in events)
    assert battle.mines[0].revealed is True
    assert mines_for_snapshot(battle, Side.FRIENDLY)


def test_activation_on_mine_triggers_aoe():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=4,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(20, 20), "friendly_combat_engineers")
    foe = _enemy("o1", Hex(22, 20))
    battle.units = {eng.unit_instance_id: eng, foe.unit_instance_id: foe}
    battle.activation = ActivationState(activation_id="a1", actor_id=eng.unit_instance_id, actions=ActionPool())
    # Empty adjacent plant — foe walks onto it later.
    resolve_deploy_mine(catalog, battle, eng, Hex(21, 20))
    assert len(battle.mines) == 1
    foe.position = Hex(21, 20)
    events = check_unit_triggers_mines(catalog, battle, foe, reason="activation_start")
    assert any(e.type == "mine_triggered" for e in events)
    assert any(e.type == "damage_applied" for e in events)
    assert battle.mines == []


def test_plant_under_enemy_detonates_immediately():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=44,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(20, 20), "friendly_combat_engineers")
    foe = _enemy("o1", Hex(21, 20))
    battle.units = {eng.unit_instance_id: eng, foe.unit_instance_id: foe}
    battle.activation = ActivationState(activation_id="a1", actor_id=eng.unit_instance_id, actions=ActionPool())
    events = resolve_deploy_mine(catalog, battle, eng, foe.position)
    assert any(e.type == "mine_deployed" for e in events)
    assert any(e.type == "mine_triggered" for e in events)
    assert any(e.type == "damage_applied" for e in events)
    assert battle.mines == []


def test_mines_survive_serialize_roundtrip():
    from app.application.services import _deserialize_battle, _serialize_battle

    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=6,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(20, 20), "friendly_combat_engineers")
    foe = _enemy("o1", Hex(23, 20))
    battle.units = {eng.unit_instance_id: eng, foe.unit_instance_id: foe}
    battle.activation = ActivationState(activation_id="a1", actor_id=eng.unit_instance_id, actions=ActionPool())
    plant = Hex(21, 20)
    resolve_deploy_mine(catalog, battle, eng, plant)
    assert len(battle.mines) == 1
    mine_id = battle.mines[0].mine_id

    restored = _deserialize_battle(_serialize_battle(battle))
    assert len(restored.mines) == 1
    assert restored.mines[0].mine_id == mine_id
    assert restored.mines[0].position == plant
    assert restored.mines[0].armed is True
    assert restored.mines[0].side == Side.FRIENDLY

    foe.position = plant
    events = check_unit_triggers_mines(catalog, restored, foe, reason="activation_start")
    assert any(e.type == "mine_triggered" for e in events)
    assert restored.mines == []


def test_deploy_mine_offered_as_standard_option():
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=5,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(20, 20), "friendly_combat_engineers")
    battle.units = {eng.unit_instance_id: eng}
    battle.activation = ActivationState(activation_id="a1", actor_id=eng.unit_instance_id, actions=ActionPool())
    opts = build_options(catalog, battle, eng, sample_moves=0)
    deploy = [o for o in opts.values() if o["subroutine"] == "deploy_mine"]
    assert deploy
    assert all(o["action_cost"] == "standard" for o in deploy)


def test_fallback_after_move_prefers_guns_not_second_dash():
    from app.engine.options import fallback_select

    catalog = load_catalog(force=True)
    # Objective center ~ (25,25) on 50x50
    battle = BattleState(
        battle_id="t",
        session_id="s",
        seed=7,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    eng = _eng("f9", Side.FRIENDLY, Hex(25, 24), "friendly_combat_engineers")
    foe = _enemy("o1", Hex(25, 26))
    battle.units = {eng.unit_instance_id: eng, foe.unit_instance_id: foe}
    battle.directives = [
        {
            "active": True,
            "scope": "global",
            "order_id": "advance_engage",
            "raw_text": "advance and engage",
            "derived_tags": ["advance", "engage"],
        }
    ]
    # Already spent the Move — Standard remains for Fire / mine.
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=eng.unit_instance_id,
        actions=ActionPool(standard=1, move=0, minor=1, moves_spent=1),
    )
    opts = build_options(catalog, battle, eng, sample_moves=8)
    chosen = opts[fallback_select(opts, eng, battle)]
    assert chosen["subroutine"] in ("attack", "deploy_mine")
    assert chosen["subroutine"] != "move"
