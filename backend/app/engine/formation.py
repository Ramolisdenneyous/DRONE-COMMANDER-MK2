"""Squad formation placement and cohesion helpers."""

from __future__ import annotations

from dataclasses import dataclass

from ..content.loader import ContentCatalog
from ..domain.hex import Hex, axial_distance, hex_key, in_bounds, offset_from_axial_delta
from .pathfinding import find_path_from
from .state import BattleState, UnitState, cohesion_ok


@dataclass
class ModelPathPlan:
    model_id: str
    path: list[Hex]
    destination: Hex


# Free aiming shuffle only — NOT a second Move. Must stay far below unit.speed.
AIM_REPOSITION_BUDGET = 2


def _spiral_offsets(max_radius: int) -> list[tuple[int, int]]:
    """Generate axial offsets in rings around origin (excluding 0,0 first then rings)."""
    offsets: list[tuple[int, int]] = [(0, 0)]
    for radius in range(1, max_radius + 1):
        # cube ring
        q, r = -radius, 0
        directions = [(1, -1), (1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1)]
        for dq, dr in directions:
            for _ in range(radius):
                offsets.append((q, r))
                q += dq
                r += dr
    return offsets


def deploy_formation(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    anchor: Hex,
    occ: dict[str, str],
) -> dict[str, Hex] | None:
    """
    Place all living models around anchor within cohesion.
    Leader (highest model number) sits on the anchor. Mutates occ with claimed hexes.
    """
    living = list(unit.living_models)
    if not living:
        return None
    cohesion = unit.speed
    positions: dict[str, Hex] = {}
    claimed: list[Hex] = []

    leader = unit.leader_model()
    ordered = []
    if leader:
        ordered.append(leader)
    ordered.extend(sorted((m for m in living if not leader or m.model_id != leader.model_id), key=lambda m: m.model_id))

    for idx, model in enumerate(ordered):
        placed = None
        candidates = [anchor] if idx == 0 else []
        for dq, dr in _spiral_offsets(cohesion):
            h = offset_from_axial_delta(anchor, dq, dr)
            if h not in candidates:
                candidates.append(h)
        for h in candidates:
            if not in_bounds(h, battle.width, battle.height):
                continue
            key = hex_key(h)
            if key in occ:
                continue
            tdef = catalog.terrain.get(battle.terrain_at(h))
            if unit.is_flying:
                if tdef and tdef.fly_move_cost is None:
                    continue
            else:
                if tdef and tdef.ground_move_cost is None:
                    continue
            trial = claimed + [h]
            if not cohesion_ok(trial, cohesion):
                continue
            placed = h
            break
        if placed is None:
            return None
        positions[model.model_id] = placed
        claimed.append(placed)
        occ[hex_key(placed)] = unit.unit_instance_id

    return positions


def plan_squad_move(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    leader_dest: Hex,
    budget: int | None = None,
) -> list[ModelPathPlan] | None:
    """
    Assign destinations and paths for every living model given a leader destination.
    Returns None if no legal cohesive formation exists.
    """
    if budget is None:
        budget = unit.speed
    living = unit.living_models
    if not living:
        return None

    leader = unit.leader_model()
    if not leader or not leader.alive:
        return None
    leader_start = unit.model_position(leader)

    # Non-squad / single living model: simple path
    if not unit.is_multi_model or len(living) == 1:
        path = find_path_from(
            catalog,
            battle,
            unit,
            leader_start,
            leader_dest,
            budget,
            pass_through_unit_id=None,
            allow_end_on_pass_through=False,
        )
        if not path:
            return None
        mid = leader.model_id if leader else living[0].model_id
        return [ModelPathPlan(model_id=mid, path=path, destination=leader_dest)]

    cohesion = unit.speed
    pass_id = unit.unit_instance_id

    # Leader must reach destination
    leader_path = find_path_from(
        catalog,
        battle,
        unit,
        leader_start,
        leader_dest,
        budget,
        pass_through_unit_id=pass_id,
        allow_end_on_pass_through=True,
        blocked_ends=set(),
    )
    if not leader_path:
        return None

    assignments: dict[str, Hex] = {leader.model_id: leader_dest}
    paths: dict[str, list[Hex]] = {leader.model_id: leader_path}
    reserved: set[str] = {hex_key(leader_dest)}

    old_leader = leader_start
    followers = [m for m in sorted(living, key=lambda m: m.model_id) if m.model_id != leader.model_id]

    for model in followers:
        start = unit.model_position(model)
        # Prefer preserving relative axial offset from old leader
        saq, sar = start.to_axial()
        laq, lar = old_leader.to_axial()
        preferred = offset_from_axial_delta(leader_dest, saq - laq, sar - lar)

        candidates: list[Hex] = []
        # Preferred first, then spiral around leader dest
        for dq2, dr2 in _spiral_offsets(cohesion):
            h = offset_from_axial_delta(leader_dest, dq2, dr2)
            if h not in candidates:
                candidates.append(h)
        if preferred not in candidates:
            candidates.insert(0, preferred)
        else:
            candidates.remove(preferred)
            candidates.insert(0, preferred)

        placed = None
        best_path: list[Hex] | None = None
        for h in candidates:
            if not in_bounds(h, battle.width, battle.height):
                continue
            key = hex_key(h)
            if key in reserved:
                continue
            trial_positions = list(assignments.values()) + [h]
            if not cohesion_ok(trial_positions, cohesion):
                continue
            path = find_path_from(
                catalog,
                battle,
                unit,
                start,
                h,
                budget,
                pass_through_unit_id=pass_id,
                allow_end_on_pass_through=True,
                blocked_ends=reserved,
            )
            if not path:
                continue
            # Prefer slightly spread: soft score by distance from leader (2-3 ideal)
            placed = h
            best_path = path
            # Accept first legal in preferred/spiral order (stable); skip densest packing at leader
            if axial_distance(h, leader_dest) >= 1 or len(followers) == 0:
                break
            # If only leader hex left legal, take it (shouldn't happen — reserved)
            break

        if placed is None or best_path is None:
            return None
        assignments[model.model_id] = placed
        paths[model.model_id] = best_path
        reserved.add(hex_key(placed))

    # Final cohesion check
    if not cohesion_ok(list(assignments.values()), cohesion):
        return None

    plans = [
        ModelPathPlan(model_id=mid, path=paths[mid], destination=assignments[mid])
        for mid in sorted(assignments.keys())
    ]
    return plans


def can_squad_reach_leader_dest(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    leader_dest: Hex,
    budget: int | None = None,
) -> bool:
    return plan_squad_move(catalog, battle, unit, leader_dest, budget) is not None


def model_can_shoot(
    catalog: ContentCatalog,
    battle: BattleState,
    from_hex: Hex,
    target_hex: Hex,
    weapon_range: int,
) -> bool:
    """Range + terrain LOS. Living models (including squadmates) never block LOS."""
    from .state import has_line_of_sight

    if axial_distance(from_hex, target_hex) > weapon_range:
        return False
    return has_line_of_sight(catalog, battle, from_hex, target_hex)


def plan_firing_repositions(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    target_hexes: Hex | list[Hex],
    weapon_range: int,
    budget: int | None = None,
) -> list[ModelPathPlan]:
    """
    Small formation shuffle so models without LOS/range can step into a firing hex.
    Budget defaults to AIM_REPOSITION_BUDGET (not unit.speed) — Attack must not
    grant a free Move-length advance toward the target.
    Cohesion ≤ speed; no stacking.
    """
    from .pathfinding import reachable_hexes_from

    if isinstance(target_hexes, Hex):
        aims = [target_hexes]
    else:
        aims = list(target_hexes)
    if not aims:
        return []
    if budget is None:
        budget = min(AIM_REPOSITION_BUDGET, unit.speed)
    living = list(unit.living_models)
    if not living:
        return []

    def can_hit_any(from_hex: Hex) -> bool:
        return any(model_can_shoot(catalog, battle, from_hex, th, weapon_range) for th in aims)

    cohesion = unit.speed
    pass_id = unit.unit_instance_id if unit.is_multi_model else None
    starts: dict[str, Hex] = {m.model_id: unit.model_position(m) for m in living}
    if all(can_hit_any(starts[m.model_id]) for m in living):
        return []

    def assign_order(m) -> tuple:
        pos = starts[m.model_id]
        dist = min(axial_distance(pos, th) for th in aims)
        # Out-of-shot models first, then farthest from the enemy (they need the forward hexes)
        return (0 if not can_hit_any(pos) else 1, -dist, m.model_id)

    finals: dict[str, Hex] = dict(starts)
    reserved: set[str] = set()
    plans: list[ModelPathPlan] = []

    for model in sorted(living, key=assign_order):
        start = starts[model.model_id]
        reach = reachable_hexes_from(
            catalog,
            battle,
            unit,
            start,
            budget,
            pass_through_unit_id=pass_id,
            allow_end_on_pass_through=True,
        )
        shooting: list[tuple[int, Hex]] = []
        approach: list[tuple[int, Hex]] = []
        for key, cost in reach.items():
            q, r = map(int, key.split(","))
            h = Hex(q, r)
            if key in reserved and h != start:
                continue
            trial = [finals[mid] for mid in finals if mid != model.model_id] + [h]
            if not cohesion_ok(trial, cohesion):
                continue
            nearest = min(axial_distance(h, th) for th in aims)
            if can_hit_any(h):
                shooting.append((nearest * 10 + cost, h))
            else:
                approach.append((nearest * 10 + cost, h))
        shooting.sort(key=lambda x: x[0])
        approach.sort(key=lambda x: x[0])
        dest = shooting[0][1] if shooting else (approach[0][1] if approach else start)
        if dest != start:
            path = find_path_from(
                catalog,
                battle,
                unit,
                start,
                dest,
                budget,
                pass_through_unit_id=pass_id,
                allow_end_on_pass_through=True,
                blocked_ends=reserved - {hex_key(start)},
            )
            if not path:
                dest = start
            else:
                plans.append(ModelPathPlan(model_id=model.model_id, path=path, destination=dest))
        old_key = hex_key(finals[model.model_id])
        reserved.discard(old_key)
        finals[model.model_id] = dest
        reserved.add(hex_key(dest))

    if not any(can_hit_any(finals[m.model_id]) for m in living):
        return []
    return plans


def pick_volley_target_model(
    catalog: ContentCatalog,
    battle: BattleState,
    from_hex: Hex,
    target_unit: UnitState,
    weapon_range: int,
    preferred_model_id: str | None = None,
):
    """Choose a living model on the target unit this shooter can hit; prefer preferred, then nearest."""
    living = list(target_unit.living_models)
    if not living:
        return None
    if preferred_model_id:
        pref = next((m for m in living if m.model_id == preferred_model_id), None)
        if pref and model_can_shoot(catalog, battle, from_hex, target_unit.model_position(pref), weapon_range):
            return pref
    ranked: list[tuple[int, object]] = []
    for m in living:
        th = target_unit.model_position(m)
        if model_can_shoot(catalog, battle, from_hex, th, weapon_range):
            ranked.append((axial_distance(from_hex, th), m))
    if ranked:
        ranked.sort(key=lambda x: (x[0], x[1].model_id))
        return ranked[0][1]
    # No legal shot from here — return nearest living for caller to attempt later
    living.sort(key=lambda m: (axial_distance(from_hex, target_unit.model_position(m)), m.model_id))
    return living[0]


def squad_can_engage_target(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    target_unit: UnitState,
    weapon_range: int,
) -> bool:
    """True if any model can shoot any living model of target_unit now, or after aiming reposition."""
    living = unit.living_models
    victims = target_unit.living_models
    if not living or not victims:
        return False
    aims = [target_unit.model_position(m) for m in victims]
    for m in living:
        from_hex = unit.model_position(m)
        if any(model_can_shoot(catalog, battle, from_hex, th, weapon_range) for th in aims):
            return True
    aim_budget = min(AIM_REPOSITION_BUDGET, unit.speed)
    if min(axial_distance(unit.model_position(m), th) for m in living for th in aims) > weapon_range + aim_budget:
        return False
    return bool(plan_firing_repositions(catalog, battle, unit, aims, weapon_range, budget=aim_budget))
