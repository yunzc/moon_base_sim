from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from pydantic import BaseModel, ConfigDict


class WorldConfig(BaseModel):
    """Terrain grid dimensions and regolith parameters."""

    model_config = ConfigDict(frozen=True)

    grid_w: int = 40
    grid_h: int = 40

    elevation_min_cm: float = -15.0
    elevation_max_cm: float = 15.0


@dataclass
class World:
    """Top-down grid: terrain elevation, occupancy, and placed components."""

    w: int
    h: int
    config: WorldConfig = field(default_factory=WorldConfig)
    elevation: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    occupancy: np.ndarray = field(default_factory=lambda: np.empty((0, 0), dtype=bool))
    blocks: set[tuple[int, int]] = field(default_factory=set)
    anchors: set[tuple[int, int]] = field(default_factory=set)
    pod_deployed: bool = False
    pod_inflation: float = 0.0
    airlock_docked: bool = False

    @classmethod
    def generate(cls, seed: int = 0, config: WorldConfig | None = None) -> "World":
        config = config or WorldConfig()
        rng = np.random.default_rng(seed)
        w, h = config.grid_w, config.grid_h
        elevation = rng.uniform(
            config.elevation_min_cm, config.elevation_max_cm, size=(h, w)
        )
        occupancy = np.zeros((h, w), dtype=bool)
        return cls(w=w, h=h, config=config, elevation=elevation, occupancy=occupancy)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_blocked(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return True
        return bool(self.occupancy[y][x])

    def set_block(self, x: int, y: int) -> None:
        self.blocks.add((x, y))
        self.occupancy[y][x] = True

    def set_anchor(self, x: int, y: int) -> None:
        self.anchors.add((x, y))

    def grade(self, x: int, y: int, neighborhood: int) -> None:
        """Average a cell's elevation with the surrounding ``neighborhood`` radius.

        ``neighborhood=1`` averages the 3x3 block, ``2`` the 5x5, etc.
        """
        if not self.in_bounds(x, y):
            return
        block = self.elevation[
            max(0, y - neighborhood) : y + neighborhood + 1,
            max(0, x - neighborhood) : x + neighborhood + 1,
        ]
        self.elevation[y, x] = float(block.mean())

    def excavate(self, x: int, y: int, depth: float) -> None:
        """Lower a cell's elevation by ``depth`` cm."""
        if self.in_bounds(x, y):
            self.elevation[y][x] -= depth

    def deposit(self, x: int, y: int, height: float) -> None:
        """Raise a cell's elevation by ``height`` cm."""
        if self.in_bounds(x, y):
            self.elevation[y][x] += height
