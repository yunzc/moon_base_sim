"""Sensor base class — the seam between the simulated world and the autonomy.

A sensor is mounted on a robot and *publishes* an observation at a fixed rate
(like a latched sensor topic). The autonomy reads ``sensor.latest`` rather than
the ground-truth world, so perception is mediated and carries real latency.

Each concrete sensor type defines its own observation payload (subclass of
``Observation``) and its own config (subclass of ``SensorConfig``).
"""
from __future__ import annotations

import simpy
from pydantic import BaseModel, ConfigDict


class SensorConfig(BaseModel):
    """Parameters common to every sensor."""

    model_config = ConfigDict(frozen=True)

    publish_hz: float


class Observation:
    """Base marker — whatever a sensor perceives. Subclasses define the payload."""


class Sensor:
    """A perception device mounted on a robot, publishing at a fixed rate."""

    def __init__(self, config: SensorConfig):
        self.config = config
        self.period = 1.0 / config.publish_hz
        # Eager initial publish so consumers never see a missing observation.
        self.latest: Observation = self._sample()

    def _sample(self) -> Observation:
        """Produce a fresh observation of the world. Implemented by subclasses."""
        raise NotImplementedError

    def run(self, env: simpy.Environment):
        """SimPy process: re-publish the latest observation forever, at the rate."""
        while True:
            yield env.timeout(self.period)
            self.latest = self._sample()
