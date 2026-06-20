"""Baseline policy: the phase state machine, reading a world model and emitting
commands. Pathfinding (A*) is here; robots only ever get one `step` at a time.

Completion is tracked by sequence numbers: each command to a robot carries an
incrementing ``seq``; the robot echoes the last finished ``done_seq`` in status,
so a robot is "done" when ``done_seq == the last seq we sent it``.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum, auto

from ...comms.messages import Command
from ...mission.blueprint import Blueprint
from ...mission.goals import GOALS, latched_statuses
from ...sim.config import Config
from ..navigation import next_step

Coord = tuple[int, int]


class Phase(Enum):
    DIG = auto()
    GRADE = auto()
    ANCHORS = auto()
    BLOCKS = auto()
    AIRLOCK = auto()
    INFLATE = auto()
    DONE = auto()


@dataclass
class Task:
    target: Coord
    action: str
    arg: object = None
    acted: bool = False


@dataclass
class PolicyState:
    phase: Phase = Phase.DIG
    grade_pass: int = 0
    started: bool = False
    foundation: list[Coord] = field(default_factory=list)
    plans: dict[str, list[Task]] = field(default_factory=dict)
    dig_pending: set = field(default_factory=set)
    grade_pending: set = field(default_factory=set)
    anchor_pending: set = field(default_factory=set)
    block_targets: list[Coord] = field(default_factory=list)
    airlock_issued: bool = False
    inflate_issued: bool = False


def _nearest(cells, pos: Coord) -> Coord:
    return min(cells, key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]))


class Baseline:
    def __init__(self, config: Config):
        self.config = config
        self.blueprint = Blueprint(config.blueprint)
        self.layout = config.layout
        self.state = PolicyState()
        self._sent: dict[str, int] = {}
        self._latched: dict[str, str] = {}
        self._expected = (
            len(config.robots.loaders)
            + len(config.robots.producers)
            + len(config.robots.assemblers)
        )
        self._cmds: list[Command] = []
        self.model = None

    # -- command issue + completion --------------------------------------
    def _send(self, rid: str, verb: str, args: tuple = ()) -> None:
        self._sent[rid] = self._sent.get(rid, 0) + 1
        self._cmds.append(Command(rid, self._sent[rid], verb, args))

    def _cmd_done(self, rid: str) -> bool:
        v = self.model.views.get(rid)
        return v is not None and v.done_seq == self._sent.get(rid, 0)

    def _free(self, rid: str) -> bool:
        return self._cmd_done(rid) and rid not in self.state.plans

    def _of_kind(self, kind: str):
        m = self.model.views
        return [m[r] for r in sorted(m) if m[r].kind == kind]

    def _loader_cap(self, rid: str) -> int:
        return self.config.robots.loaders[int(rid[1:])].loader_capacity

    def _per_block(self, rid: str) -> int:
        return self.config.robots.producers[int(rid[1:])].regolith_per_block

    def _spoil_cell(self, pos: Coord) -> Coord:
        """Nearest cell just outside the foundation perimeter, radially out from ``pos``."""
        obs = self.model.obs
        cx, cy = self.blueprint.config.pod_center
        r = self.blueprint.config.berm_radius
        dx, dy = pos[0] - cx, pos[1] - cy
        if dx * dx + dy * dy > r * r:
            return pos
        if dx == 0 and dy == 0:
            dx = 1
        scale = (r + 1) / math.hypot(dx, dy)
        x = min(max(int(round(cx + dx * scale)), 0), obs.w - 1)
        y = min(max(int(round(cy + dy * scale)), 0), obs.h - 1)
        return (x, y)

    # -- per-robot journey driver (walk-then-act) ------------------------
    def _fire(self, view, task: Task) -> None:
        if task.action in ("excavate", "grade", "unload_ground", "place"):
            self._send(view.rid, task.action, (task.target,))
        elif task.action == "feed":
            self._send(view.rid, "feed", (task.arg,))
        elif task.action == "pickup":
            self._send(view.rid, "pickup", (task.arg,))

    def _drive(self, view, task: Task) -> bool:
        if not self._cmd_done(view.rid):
            return False
        if view.pos != task.target:
            direction = next_step(self.model.obs, view.pos, task.target)
            if direction is not None:
                self._send(view.rid, "step", (direction,))
            return False
        if not task.acted:
            self._fire(view, task)
            task.acted = True
            return False
        return True

    def _advance(self) -> None:
        for rid in list(self.state.plans):
            plan = self.state.plans[rid]
            view = self.model.views.get(rid)
            if not plan:
                del self.state.plans[rid]
                continue
            if view is not None and self._drive(view, plan[0]):
                plan.pop(0)
            if not self.state.plans.get(rid):
                self.state.plans.pop(rid, None)

    # -- entry -----------------------------------------------------------
    def decide(self, model) -> list[Command]:
        self.model = model
        self._cmds = []
        if model.obs is None or len(model.views) < self._expected:
            return []
        latched_statuses(model.obs, self.blueprint, self._latched)
        if not self.state.started:
            self.state.foundation = list(self.blueprint.foundation_cells(model.obs))
            self.state.dig_pending = set(self.state.foundation)
            self.state.started = True
        self._advance()
        getattr(self, f"_{self.state.phase.name.lower()}")()
        return self._cmds

    def mission_done(self, model) -> bool:
        return len(self._latched) >= len(GOALS)

    # -- phase handlers --------------------------------------------------
    def _dig(self) -> None:
        loaders = self._of_kind("loader")
        for v in loaders:
            if not self._free(v.rid):
                continue
            if v.regolith >= self._loader_cap(v.rid):
                self.state.plans[v.rid] = [Task(self._spoil_cell(v.pos), "unload_ground")]
            elif self.state.dig_pending:
                cell = _nearest(self.state.dig_pending, v.pos)
                self.state.dig_pending.discard(cell)
                self.state.plans[v.rid] = [Task(cell, "excavate")]
            elif v.regolith > 0:
                self.state.plans[v.rid] = [Task(self._spoil_cell(v.pos), "unload_ground")]
        if not self.state.dig_pending and all(
            self._free(v.rid) and v.regolith == 0 for v in loaders
        ):
            self.state.phase = Phase.GRADE
            self.state.grade_pass = 0
            self.state.grade_pending = set(self.state.foundation)

    def _grade(self) -> None:
        loaders = self._of_kind("loader")
        for v in loaders:
            if self._free(v.rid) and self.state.grade_pending:
                cell = _nearest(self.state.grade_pending, v.pos)
                self.state.grade_pending.discard(cell)
                self.state.plans[v.rid] = [Task(cell, "grade")]
        if not self.state.grade_pending and all(self._free(v.rid) for v in loaders):
            self.state.grade_pass += 1
            if "site_prep" in self._latched or self.state.grade_pass >= 5:
                self.state.phase = Phase.ANCHORS
                self.state.anchor_pending = set(self.blueprint.anchor_cells())
            else:
                self.state.grade_pending = set(self.state.foundation)

    def _anchors(self) -> None:
        if "anchors" in self._latched:
            self.state.phase = Phase.BLOCKS
            self.state.block_targets = list(self.blueprint.dome_floor_cells())
            return
        for v in self._of_kind("assembler"):
            if not self._free(v.rid) or not self.state.anchor_pending:
                continue
            cell = _nearest(self.state.anchor_pending, v.pos)
            self.state.anchor_pending.discard(cell)
            self.state.plans[v.rid] = [
                Task(self.layout.assembler_depot, "pickup", "anchor"),
                Task(cell, "place"),
            ]

    def _blocks(self) -> None:
        if "blocks" in self._latched:
            self.state.phase = Phase.AIRLOCK
            return
        loaders = self._of_kind("loader")
        producers = self._of_kind("producer")
        assemblers = self._of_kind("assembler")
        for v in loaders:
            if not self._free(v.rid):
                continue
            if v.regolith >= self._loader_cap(v.rid):
                target = min(producers, key=lambda p: p.regolith_inventory)
                self.state.plans[v.rid] = [Task(target.pos, "feed", target.rid)]
            else:
                pit = _nearest(self.layout.regolith_pits, v.pos)
                self.state.plans[v.rid] = [Task(pit, "excavate")]
        for p in producers:
            if self._free(p.rid) and p.regolith_inventory >= self._per_block(p.rid):
                self._send(p.rid, "produce")
        for v in assemblers:
            if not self._free(v.rid) or not self.state.block_targets:
                continue
            if not self.model.available_blocks:
                continue
            _producer_rid, source = self.model.available_blocks.pop(0)
            target = self.state.block_targets.pop(0)
            self.state.plans[v.rid] = [
                Task(source, "pickup", "block"),
                Task(target, "place"),
            ]

    def _airlock(self) -> None:
        if "airlock_docked" in self._latched:
            self.state.phase = Phase.INFLATE
            return
        assemblers = self._of_kind("assembler")
        if not assemblers:
            return
        docker = assemblers[0]
        if not self.state.airlock_issued and self._free(docker.rid):
            self.state.plans[docker.rid] = [
                Task(self.layout.assembler_depot, "pickup", "airlock"),
                Task(self.blueprint.airlock_cell(), "place"),
            ]
            self.state.airlock_issued = True

    def _inflate(self) -> None:
        if "pod_inflated" in self._latched:
            self.state.phase = Phase.DONE
            return
        assemblers = self._of_kind("assembler")
        if not assemblers:
            return
        docker = assemblers[0]
        if not self.state.inflate_issued and self._free(docker.rid):
            self._send(docker.rid, "inflate")
            self.state.inflate_issued = True

    def _done(self) -> None:
        pass
