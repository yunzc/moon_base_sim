from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Iterable

from .config import CONFIG


@dataclass
class World:
    """Top-down grid: terrain elevation, occupancy, and placed components."""

    w: int
    h: int
    elevation: list[list[float]] = field(default_factory=list)
    occupancy: list[list[bool]] = field(default_factory=list)
    blocks: set[tuple[int, int]] = field(default_factory=set)
    anchors: set[tuple[int, int]] = field(default_factory=set)
    pod_deployed: bool = False
    airlock_docked: bool = False
    phase: int = 0
    phase_label: str = "init"
    finish_time: float = 0.0

    @classmethod
    def generate(cls, seed: int = 0) -> "World":
        rng = random.Random(seed)
        w, h = CONFIG.grid_w, CONFIG.grid_h
        elevation = [
            [rng.uniform(-15.0, 15.0) for _ in range(w)] for _ in range(h)
        ]
        occupancy = [[False for _ in range(w)] for _ in range(h)]
        return cls(w=w, h=h, elevation=elevation, occupancy=occupancy)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_blocked(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return True
        return self.occupancy[y][x]

    def set_block(self, x: int, y: int) -> None:
        self.blocks.add((x, y))
        self.occupancy[y][x] = True

    def set_anchor(self, x: int, y: int) -> None:
        self.anchors.add((x, y))

    def grade(self, x: int, y: int) -> None:
        if self.in_bounds(x, y):
            self.elevation[y][x] *= 0.2

    def foundation_cells(self) -> Iterable[tuple[int, int]]:
        cx, cy = CONFIG.pod_center
        r = CONFIG.berm_radius
        for y in range(max(0, cy - r), min(self.h, cy + r + 1)):
            for x in range(max(0, cx - r), min(self.w, cx + r + 1)):
                dx, dy = x - cx, y - cy
                if dx * dx + dy * dy <= r * r:
                    yield x, y

    def foundation_variance_cm(self) -> float:
        cells = list(self.foundation_cells())
        if not cells:
            return 0.0
        vals = [abs(self.elevation[y][x]) for x, y in cells]
        return sum(vals) / len(vals)
