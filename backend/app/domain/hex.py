"""Odd-r offset hex map utilities (rectangular battlemat).

Map coordinates Hex(q, r) are stored as odd-r offset (col, row) so a W×H
grid fills a rectangle on screen. Algorithms convert to axial/cube.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


# Axial neighbor offsets (cube/axial space)
AXIAL_NEIGHBOR_OFFSETS: tuple[tuple[int, int], ...] = (
    (1, 0),
    (1, -1),
    (0, -1),
    (-1, 0),
    (-1, 1),
    (0, 1),
)

# Back-compat alias
NEIGHBOR_OFFSETS = AXIAL_NEIGHBOR_OFFSETS


def offset_to_axial(col: int, row: int) -> tuple[int, int]:
    """odd-r offset (col, row) → axial (q, r)."""
    q = col - (row - (row & 1)) // 2
    r = row
    return q, r


def axial_to_offset(q: int, r: int) -> tuple[int, int]:
    """axial (q, r) → odd-r offset (col, row)."""
    col = q + (r - (r & 1)) // 2
    row = r
    return col, row


@dataclass(frozen=True, slots=True, order=True)
class Hex:
    """Map hex in odd-r offset coordinates: q=col, r=row."""

    q: int
    r: int

    @property
    def s(self) -> int:
        aq, ar = offset_to_axial(self.q, self.r)
        return -aq - ar

    def to_axial(self) -> tuple[int, int]:
        return offset_to_axial(self.q, self.r)

    def neighbors(self) -> list["Hex"]:
        aq, ar = offset_to_axial(self.q, self.r)
        out: list[Hex] = []
        for dq, dr in AXIAL_NEIGHBOR_OFFSETS:
            col, row = axial_to_offset(aq + dq, ar + dr)
            out.append(Hex(col, row))
        return out

    def to_dict(self) -> dict:
        return {"q": self.q, "r": self.r}


def axial_distance(a: Hex, b: Hex) -> int:
    """Hex distance on the offset map (via axial conversion)."""
    aq, ar = offset_to_axial(a.q, a.r)
    bq, br = offset_to_axial(b.q, b.r)
    return (abs(aq - bq) + abs(ar - br) + abs((-aq - ar) - (-bq - br))) // 2


def in_bounds(h: Hex, width: int = 50, height: int = 50) -> bool:
    return 0 <= h.q < width and 0 <= h.r < height


def hex_key(h: Hex) -> str:
    return f"{h.q},{h.r}"


def parse_hex(data: dict | Hex) -> Hex:
    if isinstance(data, Hex):
        return data
    return Hex(int(data["q"]), int(data["r"]))


def cube_line(a: Hex, b: Hex) -> list[Hex]:
    """Deterministic line from a to b inclusive (offset cells via axial lerp)."""
    n = axial_distance(a, b)
    if n == 0:
        return [a]
    aq, ar = offset_to_axial(a.q, a.r)
    bq, br = offset_to_axial(b.q, b.r)
    results: list[Hex] = []
    for i in range(n + 1):
        t = i / n
        q = aq + (bq - aq) * t
        r = ar + (br - ar) * t
        rq, rr = _cube_round(q, r)
        col, row = axial_to_offset(rq, rr)
        results.append(Hex(col, row))
    return results


def _cube_round(fq: float, fr: float) -> tuple[int, int]:
    fs = -fq - fr
    q = round(fq)
    r = round(fr)
    s = round(fs)
    q_diff = abs(q - fq)
    r_diff = abs(r - fr)
    s_diff = abs(s - fs)
    if q_diff > r_diff and q_diff > s_diff:
        q = -r - s
    elif r_diff > s_diff:
        r = -q - s
    return q, r


def hexes_in_radius(center: Hex, radius: int, width: int = 50, height: int = 50) -> list[Hex]:
    out: list[Hex] = []
    # Offset bounding box is slightly loose; filter by true hex distance
    for col in range(center.q - radius, center.q + radius + 1):
        for row in range(center.r - radius, center.r + radius + 1):
            h = Hex(col, row)
            if in_bounds(h, width, height) and axial_distance(center, h) <= radius:
                out.append(h)
    return out


def offset_from_axial_delta(anchor: Hex, dq: int, dr: int) -> Hex:
    """Apply an axial delta to an offset-map hex; return offset result."""
    aq, ar = offset_to_axial(anchor.q, anchor.r)
    col, row = axial_to_offset(aq + dq, ar + dr)
    return Hex(col, row)


def iter_map(width: int = 50, height: int = 50) -> Iterable[Hex]:
    for r in range(height):
        for q in range(width):
            yield Hex(q, r)
