"""Reusable autonomy client: build a world model from telemetry, run a policy.

A new autonomy only needs a policy with ``decide(model) -> [Command]`` and
``mission_done(model) -> bool``; this harness handles the zmq plumbing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..comms.messages import BLOCKS, OBS, STATUS


@dataclass
class RobotView:
    rid: str
    kind: str
    pos: tuple[int, int]
    is_idle: bool
    carrying: Optional[str]
    regolith: int
    regolith_inventory: int
    done_seq: int


class Model:
    """Latest world state assembled from telemetry messages."""

    def __init__(self):
        self.obs = None                                       # latest GtObservation
        self.views: dict[str, RobotView] = {}                 # rid -> RobotView
        self.available_blocks: list[tuple[str, tuple[int, int]]] = []  # (producer_rid, coord)

    def update(self, topic: str, msg) -> None:
        if topic == OBS:
            self.obs = msg
        elif topic == STATUS:
            self.views[msg.rid] = RobotView(
                msg.rid, msg.kind, msg.pos, msg.is_idle, msg.carrying,
                msg.regolith, msg.regolith_inventory, msg.done_seq,
            )
        elif topic == BLOCKS:
            self.available_blocks.append((msg.producer_rid, msg.coord))


def run(policy, endpoint, poll_ms: int = 5) -> None:
    """Poll telemetry, decide, publish — until the policy reports mission done."""
    model = Model()
    while True:
        for topic, msg in endpoint.poll(poll_ms):
            model.update(topic, msg)
        for cmd in policy.decide(model):
            endpoint.send(cmd)
        if policy.mission_done(model):
            return
