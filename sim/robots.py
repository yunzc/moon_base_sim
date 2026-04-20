from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import simpy

from .config import CONFIG
from .pathfinding import astar
from .world import World


@dataclass
class Robot:
    rid: str
    kind: str
    x: int
    y: int
    color: tuple[int, int, int]
    state: str = "idle"
    carrying: Optional[str] = None
    battery: float = 100.0

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)


def _passable(world: World, self_pos: tuple[int, int]):
    def ok(x: int, y: int) -> bool:
        if not world.in_bounds(x, y):
            return False
        if (x, y) == self_pos:
            return True
        return not world.occupancy[y][x]

    return ok


def move_to(
    env: simpy.Environment,
    world: World,
    robot: Robot,
    goal: tuple[int, int],
    speed: float,
):
    """SimPy process: step robot along an A* path toward goal."""
    while robot.pos != goal:
        path = astar(robot.pos, goal, _passable(world, robot.pos))
        if not path or len(path) < 2:
            yield env.timeout(0.5)
            continue
        next_cell = path[1]
        nx, ny = next_cell
        if world.is_blocked(nx, ny) and next_cell != goal:
            yield env.timeout(0.2)
            continue
        yield env.timeout(1.0 / max(speed, 0.1))
        robot.x, robot.y = nx, ny
        robot.battery = max(0.0, robot.battery - 0.05)


# ---------------------------------------------------------------------------
# Phase 1 — Site Preparation
# ---------------------------------------------------------------------------


def loader_grade(
    env: simpy.Environment,
    world: World,
    robot: Robot,
    targets: simpy.Store,
    done: simpy.Event,
):
    while True:
        if not targets.items:
            if done.triggered:
                return
            yield env.timeout(0.2)
            continue
        cell = yield targets.get()
        if not isinstance(cell, tuple):
            continue
        robot.state = "grading"
        yield env.process(move_to(env, world, robot, cell, CONFIG.loader_speed))
        yield env.timeout(CONFIG.grade_time)
        world.grade(*cell)
        robot.state = "idle"


# ---------------------------------------------------------------------------
# Phase 2 — Protective Shell
# ---------------------------------------------------------------------------


def producer_loop(
    env: simpy.Environment,
    world: World,
    robot: Robot,
    block_store: simpy.Store,
    stop: simpy.Event,
):
    robot.state = "producing"
    while not stop.triggered:
        yield env.timeout(CONFIG.produce_time)
        if stop.triggered:
            break
        yield block_store.put(robot.pos)
        robot.battery = max(0.0, robot.battery - 1.0)


def assembler_anchor(
    env: simpy.Environment,
    world: World,
    robot: Robot,
    anchor_queue: simpy.Store,
    done: simpy.Event,
):
    while True:
        if not anchor_queue.items:
            if done.triggered:
                return
            yield env.timeout(0.2)
            continue
        cell = yield anchor_queue.get()
        if not isinstance(cell, tuple):
            continue
        robot.state = "anchoring"
        yield env.process(move_to(env, world, robot, cell, CONFIG.assembler_speed))
        yield env.timeout(CONFIG.anchor_drive_time)
        world.set_anchor(*cell)
        robot.state = "idle"


def assembler_build(
    env: simpy.Environment,
    world: World,
    robot: Robot,
    block_queue: simpy.Store,
    placements: simpy.Store,
    done: simpy.Event,
):
    while True:
        if not placements.items:
            if done.triggered:
                return
            yield env.timeout(0.2)
            continue
        target = yield placements.get()
        if not isinstance(target, tuple):
            continue
        robot.state = "fetch_block"
        _ = yield block_queue.get()
        robot.carrying = "block"
        robot.state = "placing"
        yield env.process(move_to(env, world, robot, target, CONFIG.assembler_speed))
        yield env.timeout(CONFIG.block_place_time)
        world.set_block(*target)
        robot.carrying = None
        robot.state = "idle"


# ---------------------------------------------------------------------------
# Phase 3 — Deployment & Docking
# ---------------------------------------------------------------------------


def docker_process(
    env: simpy.Environment,
    world: World,
    robot: Robot,
    airlock_cell: tuple[int, int],
):
    robot.state = "docking"
    yield env.process(move_to(env, world, robot, airlock_cell, CONFIG.assembler_speed))
    yield env.timeout(CONFIG.dock_time)
    world.airlock_docked = True
    world.pod_deployed = True
    robot.state = "idle"
