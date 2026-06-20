from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from ..mission.blueprint import BlueprintConfig
from .robots import RobotsConfig
from .world import WorldConfig


class SimConfig(BaseModel):
    """Runtime and presentation parameters."""

    model_config = ConfigDict(frozen=True)

    cell_size: int
    sim_speed: float     # × real-time: sim-seconds per wall-second (1.0 = real-time, 50 = 50× faster)
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
    """zmq addresses for the sim/autonomy split."""

    model_config = ConfigDict(frozen=True)

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
    comms: CommsConfig


def load_config(
    sim_path: str | Path = None,
    fleet_path: str | Path = None,
    blueprint_path: str | Path = None,
    comms_path: str | Path = None,
) -> Config:
    """Parse YAML files into a fully-specified :class:`Config`.

    Args:
        sim_path: Path to simulation config (world, sensors, etc.)
        fleet_path: Path to fleet config (robots, layout)
        blueprint_path: Path to blueprint config
        comms_path: Path to comms config

    All paths are optional but the combined data must form a valid Config.
    """
    data = {}

    if sim_path:
        with open(sim_path) as f:
            data.update(yaml.safe_load(f))

    if fleet_path:
        with open(fleet_path) as f:
            data.update(yaml.safe_load(f))

    if blueprint_path:
        with open(blueprint_path) as f:
            data.update(yaml.safe_load(f))

    if comms_path:
        with open(comms_path) as f:
            data.update(yaml.safe_load(f))

    return Config.model_validate(data)
