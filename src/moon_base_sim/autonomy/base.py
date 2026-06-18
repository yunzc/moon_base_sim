"""Autonomy contract: the state object and the protocol implementations satisfy.

An autonomy perceives only through robot-mounted sensors and issues commands via
the robots' APIs — independent of the simulator (no SimPy, no clock). It is
invoked once per tick via :meth:`Autonomy.decide`, which must be re-entrant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..mission.blueprint import Blueprint
from ..sim.robots import Robot


@dataclass
class AutonomyState:
    """Bookkeeping owned by the autonomy module, not the physical world."""

    current_activity: str = "init"
    finish_time: float = 0.0
    goal_status: dict[str, tuple[bool, str]] = field(default_factory=dict)  # by Goal.name


class Autonomy(Protocol):
    state: AutonomyState

    def decide(self, fleet: list[Robot], blueprint: Blueprint) -> None: ...
