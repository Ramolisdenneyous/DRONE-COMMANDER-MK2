"""Seeded deterministic RNG for dice, ties, force building, and maps."""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SeededRNG:
    seed: int
    state: Any | None = None
    index: int = 0
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)
        if self.state is not None:
            self._rng.setstate(self.state)

    def snapshot_state(self) -> Any:
        return self._rng.getstate()

    def next_int(self, low: int, high: int) -> int:
        self.index += 1
        return self._rng.randint(low, high)

    def roll_dice(self, count: int, sides: int) -> list[int]:
        return [self.next_int(1, sides) for _ in range(count)]

    def roll_nd6(self, n: int = 3) -> tuple[list[int], int]:
        dice = self.roll_dice(n, 6)
        return dice, sum(dice)

    def roll_d20(self) -> int:
        return self.next_int(1, 20)

    def choice(self, items: list):
        if not items:
            raise ValueError("choice from empty sequence")
        self.index += 1
        return self._rng.choice(items)

    def shuffle(self, items: list) -> list:
        copy = list(items)
        self.index += 1
        self._rng.shuffle(copy)
        return copy


def seed_from_string(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return int(digest[:16], 16)
