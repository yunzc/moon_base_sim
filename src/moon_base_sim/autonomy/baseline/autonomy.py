"""Baseline autonomy implementation: hardcoded three-phase mission."""
from __future__ import annotations

import simpy

from ...sim.robots import Robot
from ...sim.world import World
from ..base import AutonomyState
from .phases import run_mission, spawn_fleet


class Baseline:
    """Reads ground-truth world state and dispatches robots through phases 1–3."""

    def __init__(self) -> None:
        self.state = AutonomyState()

    def spawn_fleet(self, world: World) -> list[Robot]:
        return spawn_fleet(world)

    def run(self, env: simpy.Environment, world: World, fleet: list[Robot]):
        yield from run_mission(env, world, fleet, self.state)
