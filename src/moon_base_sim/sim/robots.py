from __future__ import annotations

from enum import Enum
from typing import Optional

import simpy
from pydantic import BaseModel, ConfigDict

from ..comms.messages import BLOCKS, STATUS, BlockReady, RobotStatus
from .sensors import Sensor, SensorsConfig
from .world import World


class Direction(Enum):
    UP = (0, -1)
    DOWN = (0, 1)
    LEFT = (-1, 0)
    RIGHT = (1, 0)


_NAME_TO_DIR = {d.name.lower(): d for d in Direction}


class RobotConfig(BaseModel):
    """Base config shared by every robot — movement speed and sensors."""

    model_config = ConfigDict(frozen=True)

    speed: float
    sensors: SensorsConfig


class LoaderConfig(RobotConfig):
    """Per-loader movement speed, action durations, and work amounts."""

    grade_time: float
    excavate_time: float
    unload_time: float

    loader_capacity: int

    grade_neighborhood: int
    excavate_depth_m: float
    deposit_height_m: float


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
    """Fleet composition — one config per robot, grouped by kind."""

    model_config = ConfigDict(frozen=True)

    loaders: list[LoaderConfig]
    producers: list[ProducerConfig]
    assemblers: list[AssemblerConfig]


class Robot:
    """A body on the grid that executes commands pulled from an inbox.

    The robot publishes its status on every state change and runs one command
    at a time. Commands are addressed by ``rid`` and carry a ``seq``; the robot
    echoes the last finished ``seq`` (``done_seq``) so an autonomy can tell when
    a command has completed. No pathfinding/decisions here.
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
        endpoint,
    ):
        self.rid = rid
        self.x = x
        self.y = y
        self.config = config
        self.speed = config.speed
        self.state = "idle"
        self.battery = 100.0
        self.world = world
        self.sensors = sensors
        self._env = env
        self._endpoint = endpoint
        self._inbox = simpy.Store(env)
        self._peers: dict[str, "Robot"] = {}   # set by the Simulator
        self._cur_seq = 0
        self._done_seq = 0
        self._busy = False

    @property
    def pos(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def carrying(self) -> Optional[str]:
        return None

    @property
    def is_idle(self) -> bool:
        return not self._busy

    def deliver(self, cmd) -> None:
        """Hand a command to this robot's inbox (called by the Simulator's router)."""
        self._inbox.put(cmd)

    def heartbeat(self, period: float):
        """Re-publish status at a fixed rate so late-joining clients see idle robots."""
        while True:
            yield self._env.timeout(period)
            self._publish_status()

    def run(self):
        self._publish_status()
        while True:
            cmd = yield self._inbox.get()
            self._cur_seq = cmd.seq
            self._busy = True
            self._publish_status()
            yield from getattr(self, f"_do_{cmd.verb}")(*cmd.args)
            self._done_seq = cmd.seq
            self._busy = False
            self.state = "idle"
            self._publish_status()

    def _publish_status(self) -> None:
        self._endpoint.publish(
            STATUS,
            RobotStatus(
                rid=self.rid,
                kind=self.kind,
                pos=self.pos,
                is_idle=not self._busy,
                carrying=self.carrying,
                regolith=getattr(self, "regolith", 0),
                regolith_inventory=getattr(self, "regolith_inventory", 0),
                done_seq=self._done_seq,
                t=self._env.now,
            ),
        )

    def _do_step(self, direction: str):
        dx, dy = _NAME_TO_DIR[direction].value
        nx, ny = self.x + dx, self.y + dy
        if not self.world.in_bounds(nx, ny):
            return
        self.state = "driving"
        self._publish_status()  # Publish the "driving" state
        yield self._env.timeout(1.0 / max(self.speed, 0.1))
        self.x, self.y = nx, ny


class Loader(Robot):
    kind = "loader"
    color = (240, 180, 60)

    config: LoaderConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regolith = 0

    @property
    def carrying(self) -> Optional[str]:
        return f"reg×{self.regolith}" if self.regolith else None

    def _do_grade(self, cell: tuple[int, int]):
        self.state = "grading"
        self._publish_status()
        yield self._env.timeout(self.config.grade_time)
        self.world.grade(*cell, self.config.grade_neighborhood)

    def _do_excavate(self, cell: tuple[int, int]):
        if self.regolith >= self.config.loader_capacity:
            return
        self.state = "excavating"
        self._publish_status()
        yield self._env.timeout(self.config.excavate_time)
        self.world.excavate(*cell, self.config.excavate_depth_m)
        self.regolith += 1

    def _do_unload_ground(self, cell: tuple[int, int]):
        if self.regolith == 0:
            return
        self.state = "unloading"
        self._publish_status()
        yield self._env.timeout(self.config.unload_time)
        for _ in range(self.regolith):
            self.world.deposit(*cell, self.config.deposit_height_m)
        self.regolith = 0

    def _do_feed(self, producer_rid: str):
        if self.regolith == 0:
            return
        producer = self._peers[producer_rid]
        self.state = "feeding"
        self._publish_status()
        yield self._env.timeout(self.config.unload_time)
        producer.regolith_inventory += self.regolith
        self.regolith = 0


class Producer(Robot):
    kind = "producer"
    color = (120, 200, 240)

    config: ProducerConfig

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.regolith_inventory = 0

    @property
    def carrying(self) -> Optional[str]:
        return f"feed×{self.regolith_inventory}" if self.regolith_inventory else None

    def _do_produce(self):
        if self.regolith_inventory >= self.config.regolith_per_block:
            self.state = "producing"
            self._publish_status()
            yield self._env.timeout(self.config.produce_time)
            self.regolith_inventory -= self.config.regolith_per_block
            self._endpoint.publish(
                BLOCKS, BlockReady(self.rid, self.pos, self._env.now)
            )


class Assembler(Robot):
    kind = "assembler"
    color = (220, 120, 220)

    config: AssemblerConfig

    _PLACE_TIME = {
        "anchor": "anchor_drive_time",
        "block": "block_place_time",
        "airlock": "dock_time",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._carrying: Optional[str] = None

    @property
    def carrying(self) -> Optional[str]:
        return self._carrying

    def _do_pickup(self, item: str):
        self._carrying = item
        self.state = f"fetch_{item}"
        self._publish_status()
        yield self._env.timeout(0)

    def _do_place(self, target: tuple[int, int]):
        item = self._carrying
        self.state = f"place_{item}"
        self._publish_status()
        yield self._env.timeout(getattr(self.config, self._PLACE_TIME.get(item, "block_place_time")))
        if item == "anchor":
            self.world.set_anchor(*target)
        elif item == "block":
            self.world.set_block(*target)
        elif item == "airlock":
            self.world.airlock_docked = True
            self.world.pod_deployed = True
        self._carrying = None

    def _do_inflate(self):
        self.state = "inflating"
        self._publish_status()
        steps = 60
        for i in range(steps):
            self.world.pod_inflation = (i + 1) / steps
            yield self._env.timeout(self.config.inflate_time / steps)
