from __future__ import annotations

from typing import Optional

import simpy

from .config import CONFIG
from .pathfinding import astar
from .world import World


def _passable(world: World, self_pos: tuple[int, int]):
    def ok(x: int, y: int) -> bool:
        if not world.in_bounds(x, y):
            return False
        if (x, y) == self_pos:
            return True
        return not world.occupancy[y][x]

    return ok


class Robot:
    """Base class — anything with a position on the grid that can navigate."""

    kind: str = "robot"
    color: tuple[int, int, int] = (200, 200, 200)
    speed: float = 1.0

    def __init__(self, rid: str, x: int, y: int):
        self.rid = rid
        self.x = x
        self.y = y
        self.state = "idle"
        self.battery = 100.0

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def carrying(self) -> Optional[str]:
        return None

    def move_to(self, env: simpy.Environment, world: World, goal: tuple[int, int]):
        while self.pos != goal:
            path = astar(self.pos, goal, _passable(world, self.pos))
            if not path or len(path) < 2:
                yield env.timeout(0.5)
                continue
            nx, ny = path[1]
            if world.is_blocked(nx, ny) and (nx, ny) != goal:
                yield env.timeout(0.2)
                continue
            yield env.timeout(1.0 / max(self.speed, 0.1))
            self.x, self.y = nx, ny
            self.battery = max(0.0, self.battery - 0.05)


class Loader(Robot):
    kind = "loader"
    color = (240, 180, 60)
    speed = CONFIG.loader_speed

    def __init__(self, rid: str, x: int, y: int):
        super().__init__(rid, x, y)
        self.regolith = 0

    @property
    def carrying(self) -> Optional[str]:
        return f"reg×{self.regolith}" if self.regolith else None

    def grade(self, env: simpy.Environment, world: World, cell: tuple[int, int]):
        self.state = "grading"
        yield env.process(self.move_to(env, world, cell))
        yield env.timeout(CONFIG.grade_time)
        world.grade(*cell)
        self.state = "idle"

    def excavate(self, env: simpy.Environment, world: World, cell: tuple[int, int]):
        if self.regolith >= CONFIG.loader_capacity:
            return
        self.state = "excavating"
        yield env.process(self.move_to(env, world, cell))
        yield env.timeout(CONFIG.excavate_time)
        world.excavate(*cell)
        self.regolith += 1
        self.state = "idle"

    def unload_ground(
        self, env: simpy.Environment, world: World, cell: tuple[int, int]
    ):
        if self.regolith == 0:
            return
        self.state = "unloading"
        yield env.process(self.move_to(env, world, cell))
        yield env.timeout(CONFIG.unload_time)
        for _ in range(self.regolith):
            world.deposit(*cell)
        self.regolith = 0
        self.state = "idle"

    def unload_into(
        self, env: simpy.Environment, world: World, producer: "Producer"
    ):
        if self.regolith == 0:
            return
        self.state = "feeding"
        yield env.process(self.move_to(env, world, producer.pos))
        yield env.timeout(CONFIG.unload_time)
        producer.regolith_inventory += self.regolith
        self.regolith = 0
        self.state = "idle"


class Producer(Robot):
    kind = "producer"
    color = (120, 200, 240)
    speed = CONFIG.producer_speed

    def __init__(self, rid: str, x: int, y: int):
        super().__init__(rid, x, y)
        self.regolith_inventory = 0

    @property
    def carrying(self) -> Optional[str]:
        return f"feed×{self.regolith_inventory}" if self.regolith_inventory else None

    def run(
        self,
        env: simpy.Environment,
        world: World,
        block_store: simpy.Store,
        stop: simpy.Event,
    ):
        while not stop.triggered:
            if self.regolith_inventory >= CONFIG.regolith_per_block:
                self.state = "producing"
                yield env.timeout(CONFIG.produce_time)
                if stop.triggered:
                    break
                self.regolith_inventory -= CONFIG.regolith_per_block
                yield block_store.put(self.pos)
                self.battery = max(0.0, self.battery - 1.0)
            else:
                self.state = "waiting"
                yield env.timeout(0.5)
        self.state = "idle"


class Assembler(Robot):
    kind = "assembler"
    color = (220, 120, 220)
    speed = CONFIG.assembler_speed

    def __init__(self, rid: str, x: int, y: int):
        super().__init__(rid, x, y)
        self._carrying: Optional[str] = None

    @property
    def carrying(self) -> Optional[str]:
        return self._carrying

    def fetch_and_place(
        self,
        env: simpy.Environment,
        world: World,
        source: tuple[int, int],
        target: tuple[int, int],
        item: str,
        place_time: float,
        set_fn,
    ):
        self.state = f"fetch_{item}"
        yield env.process(self.move_to(env, world, source))
        self._carrying = item
        self.state = f"place_{item}"
        yield env.process(self.move_to(env, world, target))
        yield env.timeout(place_time)
        set_fn(*target)
        self._carrying = None
        self.state = "idle"
