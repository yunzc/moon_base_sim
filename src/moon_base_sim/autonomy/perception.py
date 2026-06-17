"""Perception helpers — how the autonomy selects an observation from a robot.

A robot carries a list of sensors; the autonomy must pick the one it needs. The
baseline wants ground truth, so it looks for the robot's :class:`GtSensor` and
reads its latched observation. A future autonomy would fuse lidar/camera
observations here instead of reaching for ground truth.
"""
from __future__ import annotations

from ..sim.robots import Robot
from ..sim.sensors import GtObservation, GtSensor


def gt_observation(robot: Robot) -> GtObservation:
    """Return the latest ground-truth observation from a robot's GtSensor."""
    for sensor in robot.sensors:
        if isinstance(sensor, GtSensor):
            return sensor.latest
    raise LookupError(f"{robot.rid} has no GtSensor mounted")
