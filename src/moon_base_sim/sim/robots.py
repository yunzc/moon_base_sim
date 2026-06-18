from __future__ import annotations

from enum import Enum
from typing import Optional

import simpy
from pydantic import BaseModel, ConfigDict

from .sensors import Sensor
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
    """A body on the grid with primitive actuators, driven by the autonomy.

    Command methods are non-blocking: they record a command that an internal
    SimPy process (:meth:`run`) executes one at a time. No pathfinding or
    decisions here — the autonomy issues primitives and polls :attr:`is_idle`.
    """

    kind: str = "robot"
    color: tuple[int, int, int] = (200, 200, 200)
    speed: float = 1.0

    def __init__(
        self,
        rid: str,
        x: int,
        y: int,
        config: RobotConfig,
        world: World,
        sensors: list[Sensor],
        env: simpy.Environment,
    ):
        self.rid = rid
        self.x = x
        self.y = y
        self.config = config
        self.speed = config.speed
        self.state = "idle"
        self.battery = 100.0
        self.world = world          # acted on (actuation)
        self.sensors = sensors      # read by the autonomy, never the world
        self._env = env
        self._cmd: Optional[tuple] = None         # current primitive, None when idle
        self._wake: Optional[simpy.Event] = None  # set while sleeping for a command

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def carrying(self) -> Optional[str]:
        return None

    @property
    def is_idle(self) -> bool:
        return self._cmd is None

    def _set_cmd(self, cmd: tuple) -> None:
        """Record a command and wake the actor if it is sleeping for one."""
        self._cmd = cmd
        if self._wake is not None and not self._wake.triggered:
            self._wake.succeed()
            self._wake = None

    def run(self):
        """SimPy process: execute the current command, else sleep until one."""
        while True:
            if self._cmd is None:
                self.state = "idle"
                self._wake = self._env.event()
                yield self._wake
                continue
            yield from self._execute(self._cmd)
            self._cmd = None

    def _execute(self, cmd: tuple):
        """Dispatch a command tuple to its ``_do_<tag>`` generator."""
        tag, *rest = cmd
        return getattr(self, f"_do_{tag}")(*rest)

    def step(self, direction: Direction) -> None:
        """Queue a single-cell cardinal move. The only movement primitive."""
        self._set_cmd(("step", direction))

    def _do_step(self, direction: Direction):
        dx, dy = direction.value
        nx, ny = self.x + dx, self.y + dy
        if not self.world.in_bounds(nx, ny):
            return
        self.state = "driving"
        yield self._env.timeout(1.0 / max(self.speed, 0.1))
        self.x, self.y = nx, ny


class Loader(Robot):
    kind = "loader"
    color = (240, 180, 60)

    config: LoaderConfig

    def __init__(
        self,
        rid: str,
        x: int,
        y: int,
        config: LoaderConfig,
        world: World,
        sensors: list[Sensor],
        env: simpy.Environment,
    ):
        super().__init__(rid, x, y, config, world, sensors, env)
        self.regolith = 0

    @property
    def carrying(self) -> Optional[str]:
        return f"reg×{self.regolith}" if self.regolith else None

    def grade(self, cell: tuple[int, int]) -> None:
        self._set_cmd(("grade", cell))

    def _do_grade(self, cell: tuple[int, int]):
        self.state = "grading"
        yield self._env.timeout(self.config.grade_time)
        self.world.grade(*cell, self.config.grade_neighborhood)
        self.state = "idle"

    def excavate(self, cell: tuple[int, int]) -> None:
        self._set_cmd(("excavate", cell))

    def _do_excavate(self, cell: tuple[int, int]):
        if self.regolith >= self.config.loader_capacity:
            return
        self.state = "excavating"
        yield self._env.timeout(self.config.excavate_time)
        self.world.excavate(*cell, self.config.excavate_depth_cm)
        self.regolith += 1
        self.state = "idle"

    def unload_ground(self, cell: tuple[int, int]) -> None:
        self._set_cmd(("unload_ground", cell))

    def _do_unload_ground(self, cell: tuple[int, int]):
        if self.regolith == 0:
            return
        self.state = "unloading"
        yield self._env.timeout(self.config.unload_time)
        for _ in range(self.regolith):
            self.world.deposit(*cell, self.config.deposit_height_cm)
        self.regolith = 0
        self.state = "idle"

    def unload_into(self, producer: "Producer") -> None:
        self._set_cmd(("unload_into", producer))

    def _do_unload_into(self, producer: "Producer"):
        if self.regolith == 0:
            return
        self.state = "feeding"
        yield self._env.timeout(self.config.unload_time)
        producer.regolith_inventory += self.regolith
        self.regolith = 0
        self.state = "idle"


class Producer(Robot):
    kind = "producer"
    color = (120, 200, 240)

    config: ProducerConfig

    def __init__(
        self,
        rid: str,
        x: int,
        y: int,
        config: ProducerConfig,
        world: World,
        sensors: list[Sensor],
        env: simpy.Environment,
    ):
        super().__init__(rid, x, y, config, world, sensors, env)
        self.regolith_inventory = 0
        self._ready: list[tuple[int, int]] = []   # source coords of finished blocks

    @property
    def carrying(self) -> Optional[str]:
        return f"feed×{self.regolith_inventory}" if self.regolith_inventory else None

    @property
    def ready_blocks(self) -> int:
        return len(self._ready)

    def take_block(self) -> Optional[tuple[int, int]]:
        """Hand off one finished block's source coord (consumed by an assembler)."""
        return self._ready.pop(0) if self._ready else None

    def produce(self) -> None:
        self._set_cmd(("produce",))

    def _do_produce(self):
        if self.regolith_inventory >= self.config.regolith_per_block:
            self.state = "producing"
            yield self._env.timeout(self.config.produce_time)
            self.regolith_inventory -= self.config.regolith_per_block
            self._ready.append(self.pos)
        self.state = "idle"


class Assembler(Robot):
    kind = "assembler"
    color = (220, 120, 220)

    config: AssemblerConfig

    # Per-item placement durations, keyed by the carried item.
    _PLACE_TIME = {
        "anchor": "anchor_drive_time",
        "block": "block_place_time",
        "airlock": "dock_time",
    }

    def __init__(
        self,
        rid: str,
        x: int,
        y: int,
        config: AssemblerConfig,
        world: World,
        sensors: list[Sensor],
        env: simpy.Environment,
    ):
        super().__init__(rid, x, y, config, world, sensors, env)
        self._carrying: Optional[str] = None

    @property
    def carrying(self) -> Optional[str]:
        return self._carrying

    def pickup(self, item: str) -> None:
        """Grab an item at the current cell. Instantaneous, no simulated time."""
        self._carrying = item
        self.state = f"fetch_{item}"

    def place(self, target: tuple[int, int]) -> None:
        self._set_cmd(("place", target))

    def _do_place(self, target: tuple[int, int]):
        item = self._carrying
        self.state = f"place_{item}"
        place_time = getattr(self.config, self._PLACE_TIME.get(item, "block_place_time"))
        yield self._env.timeout(place_time)
        if item == "anchor":
            self.world.set_anchor(*target)
        elif item == "block":
            self.world.set_block(*target)
        elif item == "airlock":
            self.world.airlock_docked = True
            self.world.pod_deployed = True
        self._carrying = None
        self.state = "idle"

    def inflate(self) -> None:
        self._set_cmd(("inflate",))

    def _do_inflate(self):
        self.state = "inflating"
        steps = 60
        duration = self.config.inflate_time
        for i in range(steps):
            self.world.pod_inflation = (i + 1) / steps
            yield self._env.timeout(duration / steps)
        self.state = "idle"
