from __future__ import annotations

from enum import Enum
from typing import Optional

import simpy
from pydantic import BaseModel, ConfigDict

from .world import World


class Direction(Enum):
    """Cardinal movement on the grid (origin top-left, so y grows downward)."""

    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


class RobotConfig(BaseModel):
    """Base config shared by every robot — movement speed."""

    model_config = ConfigDict(frozen=True)

    speed: float


class LoaderConfig(RobotConfig):
    """Per-loader movement speed, action durations, and work amounts."""

    grade_time: float
    excavate_time: float
    unload_time: float

    loader_capacity: int

    grade_neighborhood: int
    excavate_depth_cm: float
    deposit_height_cm: float


class ProducerConfig(RobotConfig):
    """Per-producer movement speed and block-production parameters."""

    produce_time: float
    regolith_per_block: int


class AssemblerConfig(RobotConfig):
    """Per-assembler movement speed and placement/docking durations."""

    anchor_drive_time: float
    block_place_time: float
    dock_time: float
    inflate_time: float


class RobotsConfig(BaseModel):
    """Fleet composition — one config per robot, grouped by kind.

    Composition is explicit: callers must supply the per-robot configs. The
    fleet size is the length of each list.
    """

    model_config = ConfigDict(frozen=True)

    loaders: list[LoaderConfig]
    producers: list[ProducerConfig]
    assemblers: list[AssemblerConfig]


class Robot:
    """Base class — anything with a position on the grid that can navigate."""

    kind: str = "robot"
    color: tuple[int, int, int] = (200, 200, 200)
    speed: float = 1.0

    def __init__(self, rid: str, x: int, y: int, config: RobotConfig):
        self.rid = rid
        self.x = x
        self.y = y
        self.config = config
        self.speed = config.speed
        self.state = "idle"
        self.battery = 100.0

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def carrying(self) -> Optional[str]:
        return None

    def step(self, env: simpy.Environment, world: World, direction: Direction):
        """Move a single cell in one cardinal direction.

        The only movement primitive a robot has — it cannot jump to an
        arbitrary cell. Deciding *where* to go (pathfinding) is the autonomy
        module's job. Guards physical bounds only; obstacle avoidance is a
        policy concern owned by the navigator.
        """
        dx, dy = direction.value
        nx, ny = self.x + dx, self.y + dy
        if not world.in_bounds(nx, ny):
            return
        yield env.timeout(1.0 / max(self.speed, 0.1))
        self.x, self.y = nx, ny
        self.battery = max(0.0, self.battery - 0.05)


class Loader(Robot):
    kind = "loader"
    color = (240, 180, 60)

    config: LoaderConfig

    def __init__(self, rid: str, x: int, y: int, config: LoaderConfig):
        super().__init__(rid, x, y, config)
        self.regolith = 0

    @property
    def carrying(self) -> Optional[str]:
        return f"reg×{self.regolith}" if self.regolith else None

    def grade(self, env: simpy.Environment, world: World, cell: tuple[int, int]):
        """Grade at the current location. Autonomy positions the loader first."""
        self.state = "grading"
        yield env.timeout(self.config.grade_time)
        world.grade(*cell, self.config.grade_neighborhood)
        self.state = "idle"

    def excavate(self, env: simpy.Environment, world: World, cell: tuple[int, int]):
        if self.regolith >= self.config.loader_capacity:
            return
        self.state = "excavating"
        yield env.timeout(self.config.excavate_time)
        world.excavate(*cell, self.config.excavate_depth_cm)
        self.regolith += 1
        self.state = "idle"

    def unload_ground(
        self, env: simpy.Environment, world: World, cell: tuple[int, int]
    ):
        if self.regolith == 0:
            return
        self.state = "unloading"
        yield env.timeout(self.config.unload_time)
        for _ in range(self.regolith):
            world.deposit(*cell, self.config.deposit_height_cm)
        self.regolith = 0
        self.state = "idle"

    def unload_into(
        self, env: simpy.Environment, world: World, producer: "Producer"
    ):
        if self.regolith == 0:
            return
        self.state = "feeding"
        yield env.timeout(self.config.unload_time)
        producer.regolith_inventory += self.regolith
        self.regolith = 0
        self.state = "idle"


class Producer(Robot):
    kind = "producer"
    color = (120, 200, 240)

    config: ProducerConfig

    def __init__(self, rid: str, x: int, y: int, config: ProducerConfig):
        super().__init__(rid, x, y, config)
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
            if self.regolith_inventory >= self.config.regolith_per_block:
                self.state = "producing"
                yield env.timeout(self.config.produce_time)
                if stop.triggered:
                    break
                self.regolith_inventory -= self.config.regolith_per_block
                yield block_store.put(self.pos)
                self.battery = max(0.0, self.battery - 1.0)
            else:
                self.state = "waiting"
                yield env.timeout(0.5)
        self.state = "idle"


class Assembler(Robot):
    kind = "assembler"
    color = (220, 120, 220)

    config: AssemblerConfig

    def __init__(self, rid: str, x: int, y: int, config: AssemblerConfig):
        super().__init__(rid, x, y, config)
        self._carrying: Optional[str] = None

    @property
    def carrying(self) -> Optional[str]:
        return self._carrying

    def pickup(self, item: str) -> None:
        """Grab an item at the current location (autonomy navigated here)."""
        self._carrying = item
        self.state = f"fetch_{item}"

    def place(
        self,
        env: simpy.Environment,
        world: World,
        target: tuple[int, int],
        place_time: float,
        set_fn,
    ):
        """Place the carried item at the current location."""
        self.state = f"place_{self._carrying}"
        yield env.timeout(place_time)
        set_fn(*target)
        self._carrying = None
        self.state = "idle"

    def inflate_pod(
        self, env: simpy.Environment, world: World, duration: float
    ):
        self.state = "inflating"
        steps = 60
        for i in range(steps):
            world.pod_inflation = (i + 1) / steps
            yield env.timeout(duration / steps)
        self.state = "idle"
