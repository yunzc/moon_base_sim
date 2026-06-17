"""Sensors: robot-mounted perception devices that publish observations at a rate."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .gt_sensor import GtObservation, GtSensor, GtSensorConfig
from .sensor import Observation, Sensor, SensorConfig

__all__ = [
    "Observation",
    "Sensor",
    "SensorConfig",
    "GtObservation",
    "GtSensor",
    "GtSensorConfig",
    "SensorsConfig",
]


class SensorsConfig(BaseModel):
    """Fleet sensor loadout config — one entry per sensor type."""

    model_config = ConfigDict(frozen=True)

    gt: GtSensorConfig
