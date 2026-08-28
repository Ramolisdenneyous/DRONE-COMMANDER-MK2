"""Limited-ammo drones rearm by returning to their deployment belt."""

from __future__ import annotations

from ..content.loader import ContentCatalog, get_catalog
from ..domain.enums import Side
from ..domain.events import DomainEvent
from ..domain.hex import Hex, axial_distance
from .state import BattleState, UnitState

# Only the Blue Direct Attack Drone reloads at the deployment belt (one micro-explosive shot).
RELOAD_AT_DEPLOY_DRONE_IDS = frozenset({"friendly_direct_attack_drone"})


def uses_deploy_reload(unit: UnitState) -> bool:
    return unit.definition_id in RELOAD_AT_DEPLOY_DRONE_IDS


def deploy_rows_for(battle: BattleState, side: Side) -> list[int]:
    catalog = get_catalog()
    mdef = catalog.maps.get(battle.map_id) if battle.map_id else None
    if side == Side.FRIENDLY:
        return list(getattr(mdef, "friendly_deploy_rows", None) or [45, 46, 47, 48, 49])
    return list(getattr(mdef, "opposition_deploy_rows", None) or [0, 1, 2, 3, 4])


def deploy_anchor(battle: BattleState, side: Side) -> Hex:
    rows = deploy_rows_for(battle, side)
    return Hex(battle.width // 2, rows[len(rows) // 2])


def hex_in_deploy(battle: BattleState, side: Side, hex_pos: Hex) -> bool:
    return hex_pos.r in deploy_rows_for(battle, side)


def needs_resupply(catalog: ContentCatalog, unit: UnitState) -> bool:
    """True when a deploy-reload drone has spent its limited ordnance."""
    if not uses_deploy_reload(unit):
        return False
    for wid in unit.weapons:
        weapon = catalog.weapons.get(wid)
        if weapon and weapon.ammo is not None and unit.ammo.get(wid, weapon.ammo) <= 0:
            return True
    return False


def has_usable_weapon(catalog: ContentCatalog, unit: UnitState) -> bool:
    """True if the unit still has at least one weapon that can fire (unlimited or ammo left)."""
    for wid in unit.weapons:
        weapon = catalog.weapons.get(wid)
        if not weapon:
            continue
        if weapon.ammo is None:
            return True
        if unit.ammo.get(wid, weapon.ammo) > 0:
            return True
    return False


def should_return_to_resupply(catalog: ContentCatalog, unit: UnitState) -> bool:
    """Soft RTB cue: Blue Direct Attack Drone with its one shot spent."""
    return unit.category == "drone" and needs_resupply(catalog, unit)


def must_return_to_resupply(catalog: ContentCatalog, unit: UnitState) -> bool:
    """Hard RTB: drone is combat-dry (every weapon empty / no unlimited backup)."""
    return unit.category == "drone" and needs_resupply(catalog, unit) and not has_usable_weapon(catalog, unit)


def resupply_unit(catalog: ContentCatalog, unit: UnitState) -> list[str]:
    restored: list[str] = []
    for wid in unit.weapons:
        weapon = catalog.weapons.get(wid)
        if not weapon or weapon.ammo is None:
            continue
        current = unit.ammo.get(wid, 0)
        if current < weapon.ammo:
            unit.ammo[wid] = weapon.ammo
            restored.append(wid)
    return restored


def try_resupply_at_deploy(catalog: ContentCatalog, battle: BattleState, unit: UnitState) -> list[DomainEvent]:
    if not uses_deploy_reload(unit) or not unit.alive:
        return []
    if not hex_in_deploy(battle, unit.side, unit.position):
        return []
    restored = resupply_unit(catalog, unit)
    if not restored:
        return []
    return [
        DomainEvent(
            type="resource_changed",
            actor_id=unit.unit_instance_id,
            payload={
                "resource": "ammo",
                "reason": "deploy_resupply",
                "restored": restored,
                "ammo": dict(unit.ammo),
            },
        )
    ]
