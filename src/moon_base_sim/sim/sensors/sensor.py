"""Sensor base class — publishes an observation on the OBS topic at a fixed rate.

Each concrete sensor type defines its own observation payload (subclass of
``Observation``) and its own config (subclass of ``SensorConfig``).
"""
from __future__ import annotations

import simpy
from pydantic import BaseModel, ConfigDict

from ...comms.messages import OBS


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

    def _sample(self) -> Observation:
        """Produce a fresh observation of the world. Implemented by subclasses."""
        raise NotImplementedError

    def run(self, env: simpy.Environment, endpoint):
        """SimPy process: publish a fresh observation on OBS forever, at the rate."""
        endpoint.publish(OBS, self._sample())
        while True:
            yield env.timeout(self.period)
            endpoint.publish(OBS, self._sample())
