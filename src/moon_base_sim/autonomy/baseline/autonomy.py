"""Baseline autonomy — thin wrapper holding policy state across ticks."""
from __future__ import annotations

from ...mission.blueprint import Blueprint
from ...sim.config import Config
from ...sim.robots import Robot
from .policy import PolicyState, decide


class Baseline:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = PolicyState()

    def decide(self, fleet: list[Robot], blueprint: Blueprint) -> None:
        decide(self.state, fleet, blueprint, self.config.layout)
