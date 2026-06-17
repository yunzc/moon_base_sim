"""Baseline autonomy implementation: hardcoded three-phase mission."""
from __future__ import annotations

import simpy

from ...mission.blueprint import Blueprint
from ...sim.config import Config
from ...sim.robots import Robot
from ...sim.world import World
from ..base import AutonomyState
from .phases import run_mission, spawn_fleet


class Baseline:
    """Perceives the world via each robot's GtSensor and dispatches phases 1–3."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = AutonomyState()

    def spawn_fleet(self, world: World) -> list[Robot]:
        return spawn_fleet(
            world, self.config.robots, self.config.layout, self.config.sensors
        )

    def run(
        self,
        env: simpy.Environment,
        fleet: list[Robot],
        blueprint: Blueprint,
    ):
        yield from run_mission(
            env, fleet, self.state, blueprint, self.config.layout
        )
