from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from ..mission.blueprint import BlueprintConfig
from .robots import RobotsConfig
from .sensors import SensorsConfig
from .world import WorldConfig


class SimConfig(BaseModel):
    """Runtime and presentation parameters."""

    model_config = ConfigDict(frozen=True)

    cell_size: int
    sim_speed: float
    target_fps: int
    tick: float          # headless decide/step granularity, sim-seconds (~1/speed)


class LayoutConfig(BaseModel):
    """Fixed site positions the baseline autonomy drives robots between."""

    model_config = ConfigDict(frozen=True)

    loader_depot: tuple[int, int]
    producer_sites: list[tuple[int, int]]
    assembler_depot: tuple[int, int]
    regolith_pits: list[tuple[int, int]]
    spoil_site: tuple[int, int]


class CommsConfig(BaseModel):
    """Real-time pacing + zmq addresses for the sim/autonomy split."""

    model_config = ConfigDict(frozen=True)

    factor: float          # wall-seconds per sim-second (RealtimeEnvironment)
    telemetry_addr: str    # sim PUB / autonomy SUB
    command_addr: str      # autonomy PUSH / sim PULL


class Config(BaseModel):
    """Root configuration — every domain config, loaded from a YAML file."""

    model_config = ConfigDict(frozen=True)

    sim: SimConfig
    world: WorldConfig
    blueprint: BlueprintConfig
    robots: RobotsConfig
    layout: LayoutConfig
    sensors: SensorsConfig
    comms: CommsConfig


def load_config(path: str | Path) -> Config:
    """Parse a YAML file into a fully-specified :class:`Config`."""
    with open(path) as f:
        data = yaml.safe_load(f)
    return Config.model_validate(data)
