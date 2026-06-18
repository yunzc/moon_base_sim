"""The sim service: terrain + robots + clock, talking only over zmq.

Owns a real-time SimPy env, the world, the fleet, and the zmq ``SimEndpoint``.
Robots publish telemetry and consume commands routed from the endpoint. Knows
nothing about any autonomy — it runs free whether or not a client is connected.
"""
from __future__ import annotations

import simpy.rt

from ..comms import SimEndpoint
from .config import Config
from .robots import Assembler, Loader, Producer, Robot
from .sensors import GtSensor
from .world import World


def build_fleet(env, world: World, config: Config, endpoint) -> list[Robot]:
    def mount() -> list[GtSensor]:
        return [GtSensor(world, config.sensors.gt)]

    layout, robots = config.layout, config.robots
    fleet: list[Robot] = []
    lx, ly = layout.loader_depot
    for i, c in enumerate(robots.loaders):
        fleet.append(Loader(f"L{i}", lx + i, ly, c, world, mount(), env, endpoint))
    for i, (c, (px, py)) in enumerate(zip(robots.producers, layout.producer_sites)):
        fleet.append(Producer(f"P{i}", px, py, c, world, mount(), env, endpoint))
    ax, ay = layout.assembler_depot
    for i, c in enumerate(robots.assemblers):
        fleet.append(Assembler(f"A{i}", ax - i, ay, c, world, mount(), env, endpoint))
    return fleet


class Simulator:
    def __init__(self, config: Config, seed: int = 0):
        self.env = simpy.rt.RealtimeEnvironment(factor=config.comms.factor, strict=False)
        self.world = World.generate(config.world, seed=seed)
        self.endpoint = SimEndpoint(config.comms.telemetry_addr, config.comms.command_addr)
        self.fleet = build_fleet(self.env, self.world, config, self.endpoint)
        self._by_id = {r.rid: r for r in self.fleet}
        status_period = 1.0 / config.sensors.gt.publish_hz
        for r in self.fleet:
            r._peers = self._by_id
            self.env.process(r.run())
            self.env.process(r.heartbeat(status_period))
            for s in r.sensors:
                self.env.process(s.run(self.env, self.endpoint))

    def route(self, commands) -> None:
        for cmd in commands:
            robot = self._by_id.get(cmd.rid)
            if robot is not None:
                robot.deliver(cmd)

    def step(self, dt: float) -> None:
        self.env.run(until=self.env.now + dt)

    @property
    def now(self) -> float:
        return self.env.now
