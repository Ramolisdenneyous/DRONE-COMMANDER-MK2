"""Control Phase — RAM allocation to drones."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("CONTENT_ROOT", str(ROOT / "content"))

import pytest

from app.application.services import _deserialize_battle, _serialize_battle
from app.content.loader import load_catalog
from app.domain.enums import Side
from app.domain.hex import Hex
from app.engine.battle import _begin_activation, end_activation
from app.engine.control_phase import (
    MAX_RAM_PER_DRONE,
    allocate_ram,
    complete_control_phase,
    control_phase_blocks_commander_actions,
    reclaim_ram,
    start_control_phase,
)
from app.engine.state import ActionPool, ActivationState, BattleState, ModelState, UnitState


def _cmd(uid: str, hex_: Hex) -> UnitState:
    return UnitState(
        unit_instance_id=uid,
        definition_id="friendly_commander",
        display_name="Commander",
        side=Side.FRIENDLY,
        category="commander",
        roles=["command"],
        asset_set_id="commander",
        position=hex_,
        speed=6,
        attack=2,
        defense=10,
        armor=14,
        models=[ModelState(model_id="m1", hp=10, max_hp=10, position=hex_)],
        weapons=["commander_shotgun"],
        abilities=[],
        movement_traits=["ground"],
        ram_current=6,
        ram_capacity=6,
        signal_range=12,
    )


def _drone(uid: str, hex_: Hex, side: Side = Side.FRIENDLY, *, size_class: str = "medium") -> UnitState:
    return UnitState(
        unit_instance_id=uid,
        definition_id="friendly_recon_drone" if side == Side.FRIENDLY else "opposition_recon_drone",
        display_name="Recon",
        side=side,
        category="drone",
        roles=["recon"],
        asset_set_id="friendly_recon" if side == Side.FRIENDLY else "opposition_recon",
        position=hex_,
        speed=8,
        attack=1,
        defense=6,
        armor=10,
        models=[ModelState(model_id="m1", hp=4, max_hp=4, position=hex_)],
        weapons=["light_cannon"],
        abilities=[],
        movement_traits=["flying"],
        size_class=size_class,
    )


def _battle(cmd: UnitState, *units: UnitState) -> BattleState:
    catalog = load_catalog(force=True)
    battle = BattleState(
        battle_id="cp-test",
        session_id="s",
        seed=1,
        content_version=catalog.content_version,
        width=50,
        height=50,
    )
    battle.units = {cmd.unit_instance_id: cmd, **{u.unit_instance_id: u for u in units}}
    battle.activation = ActivationState(
        activation_id="a1",
        actor_id=cmd.unit_instance_id,
        actions=ActionPool(),
    )
    start_control_phase(battle, cmd)
    return battle


def test_allocate_reduces_commander_ram():
    cmd = _cmd("f1", Hex(25, 25))
    drone = _drone("f2", Hex(26, 25))
    battle = _battle(cmd, drone)
    events = allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    assert any(e.type == "ram_allocated" for e in events)
    assert cmd.ram_current == 5
    assert drone.allocated_ram == 1


def test_max_three_per_drone():
    cmd = _cmd("f1", Hex(25, 25))
    drone = _drone("f2", Hex(26, 25), size_class="medium")
    battle = _battle(cmd, drone)
    for _ in range(3):
        allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    assert drone.allocated_ram == 3
    assert cmd.ram_current == 3
    with pytest.raises(ValueError, match="already has"):
        allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)


def test_small_drone_max_one_ram():
    cmd = _cmd("f1", Hex(25, 25))
    drone = _drone("f2", Hex(26, 25), size_class="small")
    battle = _battle(cmd, drone)
    allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    assert drone.allocated_ram == 1
    with pytest.raises(ValueError, match="already has 1"):
        allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    assert cmd.ram_current == 5


def test_out_of_signal_rejected():
    cmd = _cmd("f1", Hex(5, 5))
    drone = _drone("f2", Hex(40, 40))
    battle = _battle(cmd, drone)
    with pytest.raises(ValueError, match="signal"):
        allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)


def test_non_drone_rejected():
    cmd = _cmd("f1", Hex(25, 25))
    squad = UnitState(
        unit_instance_id="f9",
        definition_id="friendly_infantry_squad",
        display_name="Inf",
        side=Side.FRIENDLY,
        category="soldier_squad",
        roles=["frontline"],
        asset_set_id="blue_infantry",
        position=Hex(26, 25),
        speed=6,
        attack=1,
        defense=8,
        armor=12,
        models=[ModelState(model_id="m1", hp=5, max_hp=5, position=Hex(26, 25))],
        weapons=["rifle"],
        abilities=[],
        movement_traits=["ground"],
    )
    battle = _battle(cmd, squad)
    with pytest.raises(ValueError, match="drones"):
        allocate_ram(battle, squad.unit_instance_id, actor_side=Side.FRIENDLY)


def test_reclaim_and_complete():
    cmd = _cmd("f1", Hex(25, 25))
    drone = _drone("f2", Hex(26, 25))
    battle = _battle(cmd, drone)
    allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    reclaim_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    assert drone.allocated_ram == 0
    assert cmd.ram_current == 6
    assert control_phase_blocks_commander_actions(battle)
    complete_control_phase(battle, actor_side=Side.FRIENDLY)
    assert not control_phase_blocks_commander_actions(battle)


def test_drone_activation_gets_bonus_standards():
    catalog = load_catalog(force=True)
    cmd = _cmd("f1", Hex(25, 40))
    drone = _drone("f2", Hex(25, 25))
    drone.allocated_ram = 2
    battle = BattleState(
        battle_id="cp-act",
        session_id="s",
        seed=2,
        content_version=catalog.content_version,
        width=50,
        height=50,
        round=1,
    )
    battle.units = {cmd.unit_instance_id: cmd, drone.unit_instance_id: drone}
    battle.initiative = [drone.unit_instance_id]
    battle.initiative_index = 0
    _begin_activation(battle)
    assert battle.activation is not None
    assert battle.activation.actor_id == drone.unit_instance_id
    assert battle.activation.actions.standard == 3
    assert drone.allocated_ram == 0
    end_activation(battle)


def test_control_phase_serialize_roundtrip():
    cmd = _cmd("f1", Hex(25, 25))
    drone = _drone("f2", Hex(26, 25))
    battle = _battle(cmd, drone)
    allocate_ram(battle, drone.unit_instance_id, actor_side=Side.FRIENDLY)
    restored = _deserialize_battle(_serialize_battle(battle))
    assert restored.control_phase is not None
    assert restored.control_phase.active is True
    assert restored.units[drone.unit_instance_id].allocated_ram == 1
    assert restored.units[cmd.unit_instance_id].ram_current == 5
