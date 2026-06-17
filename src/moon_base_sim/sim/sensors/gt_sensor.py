"""Ground-truth sensor — perceives the entire world exactly.

The only sensor for now. It publishes a full-world :class:`GtObservation`, so an
autonomy mounted with it behaves as if it read the world directly (modulo the
publish-rate latency). Future sensors (lidar, camera) will subclass ``Sensor``
with their own partial/noisy observation types.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..world import World
from .sensor import Observation, Sensor, SensorConfig


class GtSensorConfig(SensorConfig):
    """Ground-truth sensor config. Own named type for future gt-specific params."""


@dataclass(frozen=True)
class GtObservation(Observation):
    """A complete, time-stamped snapshot of the world grid and placed components.

    ``elevation``/``occupancy`` are copied at sample time, so a latched
    observation is a true snapshot of the moment it was published.
    """

    w: int
    h: int
    elevation: np.ndarray
    occupancy: np.ndarray
    anchors: frozenset[tuple[int, int]]
    blocks: frozenset[tuple[int, int]]
    airlock_docked: bool
    pod_inflation: float

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.w and 0 <= y < self.h

    def is_blocked(self, x: int, y: int) -> bool:
        if not self.in_bounds(x, y):
            return True
        return bool(self.occupancy[y][x])


class GtSensor(Sensor):
    """Sees everything: samples the whole world into a :class:`GtObservation`."""

    def __init__(self, world: World, config: GtSensorConfig):
        self._world = world
        super().__init__(config)

    def _sample(self) -> GtObservation:
        w = self._world
        return GtObservation(
            w=w.w,
            h=w.h,
            elevation=w.elevation.copy(),
            occupancy=w.occupancy.copy(),
            anchors=frozenset(w.anchors),
            blocks=frozenset(w.blocks),
            airlock_docked=w.airlock_docked,
            pod_inflation=w.pod_inflation,
        )
