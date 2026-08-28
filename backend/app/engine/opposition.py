"""Opposition force builder — mirror player army, with point-cap fallback."""

from __future__ import annotations

from itertools import combinations_with_replacement

from ..content.loader import ContentCatalog
from ..domain.rng import SeededRNG


ROLE_FRONTLINE = {"frontline", "durable"}
ROLE_DAMAGE = {"mobile_damage", "area_damage", "anti_armor"}


def mirror_opposition_force(
    catalog: ContentCatalog,
    friendly_roster: list[tuple[str, int]],
) -> list[tuple[str, int]] | None:
    """Map friendly definitions to opposition counterparts via opposition_map.yaml."""
    if not friendly_roster:
        return None
    mirrored: list[tuple[str, int]] = []
    for def_id, count in friendly_roster:
        if def_id == "friendly_commander" or catalog.units.get(def_id) and catalog.units[def_id].category == "commander":
            continue
        opp_id = catalog.opposition_map.get(def_id)
        if not opp_id or opp_id not in catalog.units:
            return None
        mirrored.append((opp_id, count))
    return mirrored or None


def build_opposition_force(
    catalog: ContentCatalog,
    point_cap: int,
    rng: SeededRNG,
    max_units: int = 10,
    friendly_roster: list[tuple[str, int]] | None = None,
) -> list[tuple[str, int]]:
    """Return list of (definition_id, count) totaling <= point_cap.

    Prefer mirroring the player's army (Infantryman for infantry, etc.).
    Fall back to a point-cap composition when no mirror is available.
    """
    mirrored = mirror_opposition_force(catalog, friendly_roster or [])
    if mirrored:
        cost = sum(catalog.units[uid].point_cost * cnt for uid, cnt in mirrored)
        if cost <= point_cap:
            return mirrored

    candidates = [
        u for u in catalog.units.values()
        if "opposition" in u.side_availability and u.category != "commander"
    ]
    candidates.sort(key=lambda u: u.id)

    # Exhaustive multisets for small VS catalogs
    best: list[tuple[str, int]] | None = None
    best_score = -10**9
    top_band: list[tuple[int, list[tuple[str, int]]]] = []

    ids = [c.id for c in candidates]
    for n in range(1, max_units + 1):
        for combo in combinations_with_replacement(ids, n):
            counts: dict[str, int] = {}
            for uid in combo:
                counts[uid] = counts.get(uid, 0) + 1
            illegal = False
            cost = 0
            roles: set[str] = set()
            for uid, cnt in counts.items():
                udef = catalog.units[uid]
                if udef.max_per_army is not None and cnt > udef.max_per_army:
                    illegal = True
                    break
                cost += udef.point_cost * cnt
                roles.update(udef.roles)
            if illegal or cost > point_cap:
                continue
            has_front = bool(roles & ROLE_FRONTLINE) or any("frontline" in catalog.units[u].roles for u in counts)
            has_damage = bool(roles & ROLE_DAMAGE)
            soft_pen = 0 if (point_cap > 15 or (has_front and has_damage)) else 50
            # Prefer infantry over recovery/support fillers when filling the cap
            support_pen = sum(
                cnt * 30
                for uid, cnt in counts.items()
                if uid == "opposition_tank"
                or (
                    "support" in catalog.units[uid].roles
                    and "frontline" not in catalog.units[uid].roles
                )
            )
            util = cost
            score = util * 100 - soft_pen - support_pen - len(counts) * 2
            roster = list(counts.items())
            top_band.append((score, roster))
            if score > best_score:
                best_score = score
                best = roster

    if not top_band:
        return [("opposition_line_cell", 1)]

    top_band.sort(key=lambda x: x[0], reverse=True)
    threshold = best_score - 50
    band = [r for s, r in top_band if s >= threshold][:12]
    if not band:
        band = [best] if best else [[("opposition_line_cell", 1)]]
    chosen = rng.choice(band)
    return chosen
