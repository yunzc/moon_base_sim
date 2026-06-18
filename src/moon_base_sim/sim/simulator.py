"""The simulator: a self-contained world of terrain + robots + clock.

Owns the SimPy ``env``, the :class:`World`, and the fleet; knows nothing about
any autonomy. ``env`` is injected into the robots here, once.
"""
from __future__ import annotations

import simpy

from .config import Config
from .robots import Assembler, Loader, Producer, Robot
from .sensors import GtSensor
from .world import World


def build_fleet(env: simpy.Environment, world: World, config: Config) -> list[Robot]:
    """Construct the fleet, giving each robot its env, world, and a GtSensor."""

    def mount() -> list[GtSensor]:
        return [GtSensor(world, config.sensors.gt)]

    layout = config.layout
    robots = config.robots
    fleet: list[Robot] = []

    lx, ly = layout.loader_depot
    for i, loader_config in enumerate(robots.loaders):
        fleet.append(Loader(f"L{i}", lx + i, ly, loader_config, world, mount(), env))

    for i, (producer_config, (px, py)) in enumerate(
        zip(robots.producers, layout.producer_sites)
    ):
        fleet.append(Producer(f"P{i}", px, py, producer_config, world, mount(), env))

    ax, ay = layout.assembler_depot
    for i, assembler_config in enumerate(robots.assemblers):
        fleet.append(
            Assembler(f"A{i}", ax - i, ay, assembler_config, world, mount(), env)
        )
    return fleet


class Simulator:
    """Owns the clock, the world, and the fleet; advances time on command."""

    def __init__(self, config: Config, seed: int = 0):
        self.env = simpy.Environment()
        self.world = World.generate(config.world, seed=seed)
        self.fleet = build_fleet(self.env, self.world, config)
        for r in self.fleet:        # start each robot actor + its sensors
            self.env.process(r.run())
            for s in r.sensors:
                self.env.process(s.run(self.env))

    def step(self, dt: float) -> None:
        """Advance the simulated clock by ``dt`` sim-seconds."""
        self.env.run(until=self.env.now + dt)

    @property
    def now(self) -> float:
        return self.env.now
