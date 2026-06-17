from __future__ import annotations

import math
from typing import TYPE_CHECKING, Iterable

import numpy as np
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from ..sim.world import World


class BlueprintConfig(BaseModel):
    """Geometry and acceptance criteria of the base footprint on the grid."""

    model_config = ConfigDict(frozen=True)

    pod_center: tuple[int, int]
    dome_radius: int
    berm_radius: int
    num_anchors: int

    min_foundation_depth_cm: float
    elevation_tolerance_cm: float


class Blueprint:
    """The base footprint on the world grid, derived from a ``BlueprintConfig``."""

    def __init__(self, config: BlueprintConfig):
        self.config = config

    @property
    def pod_center(self) -> tuple[int, int]:
        return self.config.pod_center

    @property
    def dome_radius(self) -> int:
        return self.config.dome_radius

    @property
    def berm_radius(self) -> int:
        return self.config.berm_radius

    def dome_floor_cells(self) -> list[tuple[int, int]]:
        """Tiled floor of the dome: every foundation cell outside the inflated core.

        The core (Pod) inflates to ``dome_radius``; the foundation extends to
        ``berm_radius``. Blocks tile the annulus between them, sorted from
        innermost to outermost so assemblers can place without trapping
        themselves behind already-set blocks.
        """
        cx, cy = self.config.pod_center
        r_inner = self.config.dome_radius
        r_outer = self.config.berm_radius
        cells: list[tuple[int, int]] = []
        for y in range(cy - r_outer, cy + r_outer + 1):
            for x in range(cx - r_outer, cx + r_outer + 1):
                dx, dy = x - cx, y - cy
                d2 = dx * dx + dy * dy
                if r_inner * r_inner < d2 <= r_outer * r_outer:
                    cells.append((x, y))
        cells.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
        return cells

    def anchor_cells(self) -> list[tuple[int, int]]:
        """Anchor spike locations around the deflated Pod perimeter."""
        cx, cy = self.config.pod_center
        n = self.config.num_anchors
        r = self.config.dome_radius - 2
        out: list[tuple[int, int]] = []
        for i in range(n):
            theta = (2 * math.pi * i) / n
            x = int(round(cx + r * math.cos(theta)))
            y = int(round(cy + r * math.sin(theta)))
            out.append((x, y))
        return out

    def airlock_cell(self) -> tuple[int, int]:
        cx, cy = self.config.pod_center
        return (cx + self.config.berm_radius + 1, cy)

    def foundation_cells(self, world: "World") -> Iterable[tuple[int, int]]:
        cx, cy = self.config.pod_center
        r = self.config.berm_radius
        for y in range(max(0, cy - r), min(world.h, cy + r + 1)):
            for x in range(max(0, cx - r), min(world.w, cx + r + 1)):
                dx, dy = x - cx, y - cy
                if dx * dx + dy * dy <= r * r:
                    yield x, y

    def foundation_mask(self, world: "World") -> np.ndarray:
        """Boolean grid marking the disk of radius berm_radius around the pod."""
        cx, cy = self.config.pod_center
        r = self.config.berm_radius
        ys, xs = np.ogrid[: world.h, : world.w]
        return (xs - cx) ** 2 + (ys - cy) ** 2 <= r * r

    def foundation_mean_elevation(self, world: "World") -> float:
        vals = world.elevation[self.foundation_mask(world)]
        if vals.size == 0:
            return 0.0
        return float(vals.mean())

    def foundation_variance_cm(self, world: "World") -> float:
        """Mean absolute deviation from the foundation's own mean — flatness."""
        vals = world.elevation[self.foundation_mask(world)]
        if vals.size == 0:
            return 0.0
        return float(np.abs(vals - vals.mean()).mean())
