"""Autonomy contract: the state object and the protocol implementations satisfy.

An autonomy is the "player": it perceives the world only through robot-mounted
sensors, decides what to do, and issues commands through the robots' APIs. It is
independent of the simulator — no SimPy, no ``env``, no clock. The mission spec
(blueprint, supervisor checks) lives in ``moon_base_sim.mission`` and is shared
across all autonomies.

The simulator advances time; the autonomy is invoked once per tick via
:meth:`Autonomy.decide`, which is re-entrant (it keeps its own state and only
reads robot status + issues new commands).
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
    # Keyed by mission.goals.Goal.name.
    goal_status: dict[str, tuple[bool, str]] = field(default_factory=dict)


class Autonomy(Protocol):
    state: AutonomyState

    def decide(self, fleet: list[Robot], blueprint: Blueprint) -> None:
        """Observe the fleet's sensors and issue robot commands. Called once per
        tick by the rollout loop; must be re-entrant."""
        ...
