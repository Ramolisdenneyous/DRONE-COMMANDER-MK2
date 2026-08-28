"""Freestyle scenario layouts and metadata."""

from __future__ import annotations

from ..domain.hex import Hex

OBJECTIVE_RADIUS = 5
VP_TO_WIN = 5

SCENARIO_META: dict[str, dict] = {
    "point_control": {
        "display_name": "Point Control",
        "description": "Hold the central zone uncontested at round end for 1 VP. First to 5 VP wins.",
        "objective_type": "zone_control",
        "default": True,
    },
    "four_corners": {
        "display_name": "Four Corners",
        "description": "Four zones between center and corners. Score 1 VP per zone held at round end.",
        "objective_type": "zone_control",
    },
    "hold_the_line": {
        "display_name": "Hold the Line",
        "description": "Three zones across the map midline. Score 1 VP per zone held at round end.",
        "objective_type": "zone_control",
    },
    "capture_the_flags": {
        "display_name": "Capture the Flags",
        "description": "Grab flags with a unit action. Flags move with the carrier until killed. 1 VP per flag held at round end.",
        "objective_type": "capture_flags",
    },
}


def _mid(a: int, b: int) -> int:
    return (a + b) // 2


def zone_layout(scenario_id: str, width: int, height: int) -> list[dict]:
    """Return zone dicts: id, label, q, r, radius."""
    cx, cy = width // 2, height // 2
    r = OBJECTIVE_RADIUS

    if scenario_id == "point_control":
        return [{"id": "center", "label": "Center", "q": cx, "r": cy, "radius": r}]

    if scenario_id == "four_corners":
        corners = [
            ("nw", "Northwest", 0, 0),
            ("ne", "Northeast", width - 1, 0),
            ("sw", "Southwest", 0, height - 1),
            ("se", "Southeast", width - 1, height - 1),
        ]
        return [
            {
                "id": cid,
                "label": label,
                "q": _mid(cx, cq),
                "r": _mid(cy, cr),
                "radius": r,
            }
            for cid, label, cq, cr in corners
        ]

    if scenario_id in ("hold_the_line", "capture_the_flags"):
        return [
            {"id": "left", "label": "West", "q": _mid(cx, 0), "r": cy, "radius": r},
            {"id": "center", "label": "Center", "q": cx, "r": cy, "radius": r},
            {"id": "right", "label": "East", "q": _mid(cx, width - 1), "r": cy, "radius": r},
        ]

    # Legacy / fallback
    return [{"id": "center", "label": "Center", "q": cx, "r": cy, "radius": r}]


def scenario_meta(scenario_id: str) -> dict:
    return SCENARIO_META.get(scenario_id, SCENARIO_META["point_control"])


def is_flag_scenario(scenario_id: str) -> bool:
    return scenario_id == "capture_the_flags"


def flag_spawn_hex(zone: dict) -> Hex:
    return Hex(zone["q"], zone["r"])
