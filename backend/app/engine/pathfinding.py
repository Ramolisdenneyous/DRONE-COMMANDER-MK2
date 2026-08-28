"""Pathfinding and reachable hexes."""

from __future__ import annotations

import heapq

from ..content.loader import ContentCatalog
from ..domain.hex import Hex, hex_key, in_bounds
from .state import BattleState, UnitState, move_cost


def find_path_from(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    start: Hex,
    destination: Hex,
    budget: int | None = None,
    *,
    pass_through_unit_id: str | None = None,
    blocked_ends: set[str] | None = None,
    allow_end_on_pass_through: bool = False,
) -> list[Hex] | None:
    """
    Path from start to destination.

    Models of `pass_through_unit_id` (typically the same squad) do not block movement
    and do not add friendly pass-through cost. Final hex must not be occupied by a
    foreign unit. Ending on a squadmate hex is allowed only when
    allow_end_on_pass_through is True (simultaneous formation move). blocked_ends
    reserves destinations already claimed by other models in the plan.
    """
    if budget is None:
        budget = unit.speed
    dest_key = hex_key(destination)
    blocked_ends = blocked_ends or set()
    if start == destination:
        if dest_key in blocked_ends:
            return None
        return [start]
    if not in_bounds(destination, battle.width, battle.height):
        return None

    pass_id = pass_through_unit_id
    occ = battle.occupancy()

    frontier: list[tuple[int, int, Hex]] = []
    counter = 0
    heapq.heappush(frontier, (0, counter, start))
    came_from: dict[str, Hex | None] = {hex_key(start): None}
    cost_so_far: dict[str, int] = {hex_key(start): 0}

    while frontier:
        current_cost, _, current = heapq.heappop(frontier)
        if current == destination:
            break
        for nb in current.neighbors():
            if not in_bounds(nb, battle.width, battle.height):
                continue
            step = move_cost(catalog, battle, unit, nb)
            if step is None:
                continue
            nk = hex_key(nb)
            occupant = occ.get(nk)
            extra = 0
            if occupant:
                if pass_id and occupant == pass_id:
                    extra = 0
                elif occupant == unit.unit_instance_id:
                    extra = 0
                else:
                    other = battle.units.get(occupant)
                    if not other or other.side != unit.side:
                        continue
                    extra = 1
            new_cost = current_cost + step + extra
            if new_cost > budget:
                continue
            if nk not in cost_so_far or new_cost < cost_so_far[nk]:
                cost_so_far[nk] = new_cost
                counter += 1
                heapq.heappush(frontier, (new_cost, counter, nb))
                came_from[nk] = current

    if dest_key not in came_from:
        return None

    if dest_key in blocked_ends:
        return None

    occ_end = occ.get(dest_key)
    if occ_end:
        if pass_id and occ_end == pass_id:
            if not allow_end_on_pass_through:
                return None
        elif occ_end != unit.unit_instance_id:
            return None

    path: list[Hex] = []
    cur: Hex | None = destination
    while cur is not None:
        path.append(cur)
        prev = came_from[hex_key(cur)]
        cur = prev
    path.reverse()
    return path


def find_path(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    destination: Hex,
    budget: int | None = None,
) -> list[Hex] | None:
    start = unit.model_position(unit.leader_model()) if unit.is_multi_model else unit.position
    return find_path_from(
        catalog,
        battle,
        unit,
        start,
        destination,
        budget,
        pass_through_unit_id=unit.unit_instance_id if unit.is_multi_model else None,
    )


def reachable_hexes_from(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    start: Hex,
    budget: int | None = None,
    *,
    pass_through_unit_id: str | None = None,
    allow_end_on_pass_through: bool = False,
) -> dict[str, int]:
    if budget is None:
        budget = unit.speed
    pass_id = pass_through_unit_id or (unit.unit_instance_id if unit.is_multi_model else None)
    occ = battle.occupancy()
    frontier: list[tuple[int, int, Hex]] = []
    counter = 0
    heapq.heappush(frontier, (0, counter, start))
    cost_so_far: dict[str, int] = {hex_key(start): 0}

    while frontier:
        current_cost, _, current = heapq.heappop(frontier)
        for nb in current.neighbors():
            if not in_bounds(nb, battle.width, battle.height):
                continue
            step = move_cost(catalog, battle, unit, nb)
            if step is None:
                continue
            nk = hex_key(nb)
            occupant = occ.get(nk)
            extra = 0
            if occupant and occupant != pass_id and occupant != unit.unit_instance_id:
                other = battle.units.get(occupant)
                if not other or other.side != unit.side:
                    continue
                extra = 1
            elif occupant == pass_id and pass_id:
                # Intra-squad: free pass-through
                extra = 0
            elif occupant == unit.unit_instance_id and not pass_id:
                # Own single-token hex
                extra = 0
            new_cost = current_cost + step + extra
            if new_cost > budget:
                continue
            if nk not in cost_so_far or new_cost < cost_so_far[nk]:
                cost_so_far[nk] = new_cost
                counter += 1
                heapq.heappush(frontier, (new_cost, counter, nb))

    result: dict[str, int] = {}
    for k, c in cost_so_far.items():
        if k == hex_key(start):
            result[k] = c
            continue
        occ_id = occ.get(k)
        if occ_id:
            if pass_id and occ_id == pass_id:
                if allow_end_on_pass_through:
                    result[k] = c
                # else: cannot end on squadmate — skip
                continue
            if occ_id != unit.unit_instance_id:
                continue
        result[k] = c
    return result


def reachable_hexes(
    catalog: ContentCatalog,
    battle: BattleState,
    unit: UnitState,
    budget: int | None = None,
) -> dict[str, int]:
    start = unit.model_position(unit.leader_model()) if unit.is_multi_model else unit.position
    return reachable_hexes_from(
        catalog,
        battle,
        unit,
        start,
        budget,
        pass_through_unit_id=unit.unit_instance_id if unit.is_multi_model else None,
        allow_end_on_pass_through=False,
    )
