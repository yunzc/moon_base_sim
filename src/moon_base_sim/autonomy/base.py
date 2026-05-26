"""Autonomy contract: state and the protocol implementations satisfy.

Autonomies read world state, dispatch robot commands, and report progress on
their own state object. The mission spec (blueprint, supervisor checks) lives
in ``moon_base_sim.mission`` and is shared across all autonomies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generator, Protocol

import simpy

from ..sim.robots import Robot
from ..sim.world import World


@dataclass
class AutonomyState:
    """Bookkeeping owned by the autonomy module, not the physical world."""

    current_activity: str = "init"
    finish_time: float = 0.0
    # Keyed by mission.goals.Goal.name.
    goal_status: dict[str, tuple[bool, str]] = field(default_factory=dict)


class Autonomy(Protocol):
    state: AutonomyState

    def spawn_fleet(self, world: World) -> list[Robot]: ...

    def run(
        self, env: simpy.Environment, world: World, fleet: list[Robot]
    ) -> Generator: ...
