"""Baseline autonomy: a re-entrant policy that perceives via robot sensors.

The player. It holds no ``env`` and no Simulator reference — the rollout loop
calls :meth:`decide` once per tick with the fleet (the robots' APIs) and the
blueprint (the goals).
"""
from __future__ import annotations

from ...mission.blueprint import Blueprint
from ...sim.config import Config
from ...sim.robots import Robot
from .policy import PolicyState, decide


class Baseline:
    """Drives the fleet through the mission via the per-tick :func:`policy.decide`."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = PolicyState()

    def decide(self, fleet: list[Robot], blueprint: Blueprint) -> None:
        decide(self.state, fleet, blueprint, self.config.layout)
