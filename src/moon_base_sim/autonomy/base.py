"""Autonomy contract: a policy maps the world model to robot commands.

A policy is pure with respect to the sim — it reads a :class:`client.Model`
(built from telemetry messages) and returns :class:`comms.messages.Command`s. It
never imports or holds sim objects.
"""
from __future__ import annotations

from typing import Protocol

from ..comms.messages import Command


class Autonomy(Protocol):
    def decide(self, model) -> list[Command]:
        """Return commands to publish this cycle, given the latest world model."""
        ...

    def mission_done(self, model) -> bool: ...
