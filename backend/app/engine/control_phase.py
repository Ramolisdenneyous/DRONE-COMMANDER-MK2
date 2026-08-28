"""Control Phase — allocate commander RAM to in-signal drones."""

from __future__ import annotations

from ..domain.enums import Side
from ..domain.events import DomainEvent
from .state import BattleState, ControlPhaseState, UnitState, commander_for_side, signal_radius, unit_within_radius

MAX_RAM_PER_DRONE = 3
# Small strike craft (one-ways, dogs, direct-attack) can only hold a single RAM.
MAX_RAM_PER_SMALL_DRONE = 1


def max_ram_for_drone(drone: UnitState) -> int:
    """Per-drone Control Phase cap. Small drones: 1; medium/large: 3."""
    size = (drone.size_class or "").strip().lower()
    if size == "small":
        return MAX_RAM_PER_SMALL_DRONE
    return MAX_RAM_PER_DRONE


def drone_in_commander_signal(battle: BattleState, commander: UnitState, drone: UnitState) -> bool:
    if not commander.alive or not drone.alive:
        return False
    return unit_within_radius(commander.position, drone, signal_radius(commander))


def eligible_allocation_drones(battle: BattleState, commander: UnitState) -> list[UnitState]:
    return [
        u
        for u in battle.living_units(commander.side)
        if u.category == "drone" and drone_in_commander_signal(battle, commander, u)
    ]


def start_control_phase(battle: BattleState, commander: UnitState) -> list[DomainEvent]:
    if commander.category != "commander" or commander.ram_capacity is None:
        return []
    battle.control_phase = ControlPhaseState(
        active=True,
        side=commander.side,
        commander_id=commander.unit_instance_id,
    )
    return [
        DomainEvent(
            type="control_phase_started",
            actor_id=commander.unit_instance_id,
            payload={
                "side": commander.side.value,
                "commander_id": commander.unit_instance_id,
                "ram_current": commander.ram_current,
                "ram_capacity": commander.ram_capacity,
                "eligible_drones": [u.unit_instance_id for u in eligible_allocation_drones(battle, commander)],
            },
        )
    ]


def clear_stale_allocated_ram(battle: BattleState) -> None:
    """Unused allocation cannot bank across rounds."""
    for u in battle.units.values():
        u.allocated_ram = 0


def require_control_phase(battle: BattleState) -> ControlPhaseState:
    cp = battle.control_phase
    if not cp or not cp.active:
        raise ValueError("Control Phase is not active")
    return cp


def allocate_ram(battle: BattleState, drone_id: str, *, actor_side: Side | None = None) -> list[DomainEvent]:
    cp = require_control_phase(battle)
    if actor_side is not None and cp.side != actor_side:
        raise ValueError("Wrong side for Control Phase")
    commander = battle.units.get(cp.commander_id)
    if not commander or not commander.alive or commander.category != "commander":
        raise ValueError("Commander unavailable")
    drone = battle.units.get(drone_id)
    if not drone or not drone.alive:
        raise ValueError("Drone not found")
    if drone.side != commander.side:
        raise ValueError("Can only allocate to your own drones")
    if drone.category != "drone":
        raise ValueError("RAM can only be allocated to drones")
    if not drone_in_commander_signal(battle, commander, drone):
        raise ValueError("Drone is out of signal range")
    if (commander.ram_current or 0) < 1:
        raise ValueError("No RAM remaining")
    cap = max_ram_for_drone(drone)
    if drone.allocated_ram >= cap:
        size = (drone.size_class or "drone").strip() or "drone"
        raise ValueError(f"This {size} drone already has {cap} RAM (max for its size)")

    commander.ram_current = int(commander.ram_current or 0) - 1
    drone.allocated_ram += 1
    return [
        DomainEvent(
            type="ram_allocated",
            actor_id=commander.unit_instance_id,
            payload={
                "drone_id": drone.unit_instance_id,
                "drone_allocated_ram": drone.allocated_ram,
                "drone_ram_cap": cap,
                "commander_ram_current": commander.ram_current,
            },
        ),
        DomainEvent(
            type="resource_changed",
            actor_id=commander.unit_instance_id,
            payload={
                "resource": "ram",
                "remaining": commander.ram_current,
                "reason": "allocate",
                "drone_id": drone.unit_instance_id,
            },
        ),
    ]


def reclaim_ram(battle: BattleState, drone_id: str, *, actor_side: Side | None = None) -> list[DomainEvent]:
    cp = require_control_phase(battle)
    if actor_side is not None and cp.side != actor_side:
        raise ValueError("Wrong side for Control Phase")
    commander = battle.units.get(cp.commander_id)
    if not commander or not commander.alive or commander.category != "commander":
        raise ValueError("Commander unavailable")
    drone = battle.units.get(drone_id)
    if not drone or not drone.alive:
        raise ValueError("Drone not found")
    if drone.side != commander.side:
        raise ValueError("Can only reclaim from your own drones")
    if drone.allocated_ram < 1:
        raise ValueError("Drone has no allocated RAM")

    drone.allocated_ram -= 1
    commander.ram_current = int(commander.ram_current or 0) + 1
    if commander.ram_capacity is not None:
        commander.ram_current = min(commander.ram_current, commander.ram_capacity)
    return [
        DomainEvent(
            type="ram_reclaimed",
            actor_id=commander.unit_instance_id,
            payload={
                "drone_id": drone.unit_instance_id,
                "drone_allocated_ram": drone.allocated_ram,
                "commander_ram_current": commander.ram_current,
            },
        ),
        DomainEvent(
            type="resource_changed",
            actor_id=commander.unit_instance_id,
            payload={
                "resource": "ram",
                "remaining": commander.ram_current,
                "reason": "reclaim",
                "drone_id": drone.unit_instance_id,
            },
        ),
    ]


def complete_control_phase(battle: BattleState, *, actor_side: Side | None = None) -> list[DomainEvent]:
    cp = require_control_phase(battle)
    if actor_side is not None and cp.side != actor_side:
        raise ValueError("Wrong side for Control Phase")
    commander_id = cp.commander_id
    side = cp.side
    battle.control_phase = None
    return [
        DomainEvent(
            type="control_phase_completed",
            actor_id=commander_id,
            payload={"side": side.value, "commander_id": commander_id},
        )
    ]


def control_phase_blocks_commander_actions(battle: BattleState) -> bool:
    return bool(battle.control_phase and battle.control_phase.active)


def bonus_standard_from_allocated_ram(unit: UnitState) -> int:
    return min(max_ram_for_drone(unit), max(0, int(unit.allocated_ram or 0)))


def consume_allocated_ram_into_pool(unit: UnitState) -> int:
    """Apply allocated RAM as extra Standards once, then clear the bank."""
    bonus = bonus_standard_from_allocated_ram(unit)
    unit.allocated_ram = 0
    return bonus


def control_phase_snapshot(battle: BattleState) -> dict | None:
    cp = battle.control_phase
    if not cp:
        return None
    commander = battle.units.get(cp.commander_id)
    eligible = []
    eligible_caps: dict[str, int] = {}
    if commander and commander.alive:
        for u in eligible_allocation_drones(battle, commander):
            eligible.append(u.unit_instance_id)
            eligible_caps[u.unit_instance_id] = max_ram_for_drone(u)
    return {
        "active": bool(cp.active),
        "side": cp.side.value,
        "commander_id": cp.commander_id,
        "eligible_drone_ids": eligible,
        "eligible_drone_ram_caps": eligible_caps,
        "ram_current": commander.ram_current if commander else None,
        "ram_capacity": commander.ram_capacity if commander else None,
    }
