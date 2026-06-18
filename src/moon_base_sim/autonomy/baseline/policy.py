"""Baseline policy: a re-entrant state machine driven one tick at a time.

Each tick :func:`decide` evaluates the goals, advances every robot's in-flight
plan one step, and assigns fresh work for the current phase. A robot's job is a
:class:`Task` (walk to a cell, then act) that :func:`_drive` carries across
ticks — pathfinding (A*) lives here, the robots only get single-cell steps.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from ...mission.blueprint import Blueprint
from ...mission.goals import GOALS
from ...sim.config import LayoutConfig
from ...sim.robots import Assembler, Loader, Producer, Robot
from ..base import AutonomyState
from ..navigation import next_step
from ..perception import gt_observation

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
    """One leg of a robot's job: reach ``target``, then fire ``action``."""

    target: Coord
    action: str            # "excavate" | "grade" | "unload_ground" | "feed" | ...
    arg: object = None     # carried item (pickup/place) or producer (feed)
    acted: bool = False    # has the action primitive been issued yet?


@dataclass
class PolicyState(AutonomyState):
    phase: Phase = Phase.DIG
    grade_pass: int = 0
    started: bool = False
    foundation: list[Coord] = field(default_factory=list)
    plans: dict[str, list[Task]] = field(default_factory=dict)   # rid -> plan
    dig_pending: set[Coord] = field(default_factory=set)
    grade_pending: set[Coord] = field(default_factory=set)
    anchor_pending: set[Coord] = field(default_factory=set)
    block_targets: list[Coord] = field(default_factory=list)     # inner→outer order
    airlock_issued: bool = False
    inflate_issued: bool = False


def _nearest(cells, pos: Coord) -> Coord:
    return min(cells, key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]))


def _eval_goals(state: PolicyState, obs, blueprint: Blueprint) -> None:
    """Evaluate pending goals, latching each OK (milestones stay satisfied)."""
    for goal in GOALS:
        if state.goal_status.get(goal.name, (False, ""))[0]:
            continue                                   # already achieved — latch it
        ok, reason = goal.is_done(obs, blueprint)
        state.goal_status[goal.name] = (ok, reason)
        if ok:
            print(f"[goal] {goal.name} OK : {reason}")


def _goal_ok(state: PolicyState, name: str) -> bool:
    return state.goal_status.get(name, (False, ""))[0]


def _fire_action(robot: Robot, task: Task) -> None:
    action = task.action
    if action == "excavate":
        robot.excavate(task.target)
    elif action == "grade":
        robot.grade(task.target)
    elif action == "unload_ground":
        robot.unload_ground(task.target)
    elif action == "feed":
        robot.unload_into(task.arg)
    elif action == "pickup":
        robot.pickup(task.arg)
    elif action == "place":
        robot.place(task.target)


def _drive(robot: Robot, task: Task) -> bool:
    """Carry one task forward this tick. Returns True when it is complete."""
    if not robot.is_idle:
        return False
    if robot.pos != task.target:
        direction = next_step(gt_observation(robot), robot.pos, task.target)
        if direction is not None:
            robot.step(direction)
        return False
    if not task.acted:
        _fire_action(robot, task)
        task.acted = True
        return False
    return True


def _advance(state: PolicyState, robot: Robot) -> None:
    plan = state.plans.get(robot.rid)
    if not plan:
        return
    if _drive(robot, plan[0]):
        plan.pop(0)


def _free(state: PolicyState, robot: Robot) -> bool:
    """Free for new work: idle with no remaining plan."""
    return robot.is_idle and not state.plans.get(robot.rid)


def _dig(state, fleet, blueprint, layout, obs) -> None:
    loaders = [r for r in fleet if isinstance(r, Loader)]
    for ld in loaders:
        if not _free(state, ld):
            continue
        if ld.regolith >= ld.config.loader_capacity:
            state.plans[ld.rid] = [Task(layout.spoil_site, "unload_ground")]
        elif state.dig_pending:
            cell = _nearest(state.dig_pending, ld.pos)
            state.dig_pending.discard(cell)
            state.plans[ld.rid] = [Task(cell, "excavate")]
        elif ld.regolith > 0:                       # drain leftover at end of dig
            state.plans[ld.rid] = [Task(layout.spoil_site, "unload_ground")]

    if not state.dig_pending and all(
        _free(state, ld) and ld.regolith == 0 for ld in loaders
    ):
        state.phase = Phase.GRADE
        state.grade_pass = 0
        state.grade_pending = set(state.foundation)
        state.current_activity = "Site Prep — Grade (pass 1)"


def _grade(state, fleet, blueprint, layout, obs) -> None:
    loaders = [r for r in fleet if isinstance(r, Loader)]
    for ld in loaders:
        if not _free(state, ld):
            continue
        if state.grade_pending:
            cell = _nearest(state.grade_pending, ld.pos)
            state.grade_pending.discard(cell)
            state.plans[ld.rid] = [Task(cell, "grade")]

    if not state.grade_pending and all(_free(state, ld) for ld in loaders):
        state.grade_pass += 1
        if _goal_ok(state, "site_prep") or state.grade_pass >= 5:
            state.phase = Phase.ANCHORS
            state.anchor_pending = set(blueprint.anchor_cells())
            state.current_activity = "Placing anchors"
        else:
            state.grade_pending = set(state.foundation)
            state.current_activity = f"Site Prep — Grade (pass {state.grade_pass + 1})"


def _anchors(state, fleet, blueprint, layout, obs) -> None:
    if _goal_ok(state, "anchors"):
        state.phase = Phase.BLOCKS
        state.block_targets = list(blueprint.dome_floor_cells())
        state.current_activity = "Producing blocks"
        return
    assemblers = [r for r in fleet if isinstance(r, Assembler)]
    for a in assemblers:
        if not _free(state, a) or not state.anchor_pending:
            continue
        cell = _nearest(state.anchor_pending, a.pos)
        state.anchor_pending.discard(cell)
        state.plans[a.rid] = [
            Task(layout.assembler_depot, "pickup", "anchor"),
            Task(cell, "place"),
        ]


def _blocks(state, fleet, blueprint, layout, obs) -> None:
    if _goal_ok(state, "blocks"):
        state.phase = Phase.AIRLOCK
        state.current_activity = "Docking airlock"
        return

    loaders = [r for r in fleet if isinstance(r, Loader)]
    producers = [r for r in fleet if isinstance(r, Producer)]
    assemblers = [r for r in fleet if isinstance(r, Assembler)]

    # Loaders run the supply chain: dig at pits, feed the leanest producer.
    for ld in loaders:
        if not _free(state, ld):
            continue
        if ld.regolith >= ld.config.loader_capacity:
            target = min(producers, key=lambda p: p.regolith_inventory)
            state.plans[ld.rid] = [Task(target.pos, "feed", target)]
        else:
            pit = _nearest(layout.regolith_pits, ld.pos)
            state.plans[ld.rid] = [Task(pit, "excavate")]

    # Producers convert inventory into finished blocks on their own square.
    for p in producers:
        if p.is_idle and p.regolith_inventory >= p.config.regolith_per_block:
            p.produce()

    # Assemblers pair a finished block with the next pending target.
    for a in assemblers:
        if not _free(state, a) or not state.block_targets:
            continue
        src_producer = next((p for p in producers if p.ready_blocks > 0), None)
        if src_producer is None:
            continue
        source = src_producer.take_block()
        target = state.block_targets.pop(0)
        state.plans[a.rid] = [
            Task(source, "pickup", "block"),
            Task(target, "place"),
        ]


def _airlock(state, fleet, blueprint, layout, obs) -> None:
    if _goal_ok(state, "airlock_docked"):
        state.phase = Phase.INFLATE
        state.current_activity = "Inflating pod"
        return
    docker = [r for r in fleet if isinstance(r, Assembler)][0]
    if not state.airlock_issued and _free(state, docker):
        state.plans[docker.rid] = [
            Task(layout.assembler_depot, "pickup", "airlock"),
            Task(blueprint.airlock_cell(), "place"),
        ]
        state.airlock_issued = True


def _inflate(state, fleet, blueprint, layout, obs) -> None:
    if _goal_ok(state, "pod_inflated"):
        state.phase = Phase.DONE
        state.current_activity = "Mission complete"
        return
    docker = [r for r in fleet if isinstance(r, Assembler)][0]
    if not state.inflate_issued and _free(state, docker):
        docker.inflate()
        state.inflate_issued = True


def _done(state, fleet, blueprint, layout, obs) -> None:
    pass


_PHASE_HANDLERS = {
    Phase.DIG: _dig,
    Phase.GRADE: _grade,
    Phase.ANCHORS: _anchors,
    Phase.BLOCKS: _blocks,
    Phase.AIRLOCK: _airlock,
    Phase.INFLATE: _inflate,
    Phase.DONE: _done,
}


def _init(state: PolicyState, fleet: list[Robot], blueprint: Blueprint) -> None:
    obs = gt_observation(fleet[0])
    state.foundation = list(blueprint.foundation_cells(obs))
    state.dig_pending = set(state.foundation)
    state.phase = Phase.DIG
    state.current_activity = "Site Prep — Dig"
    state.started = True


def decide(
    state: PolicyState,
    fleet: list[Robot],
    blueprint: Blueprint,
    layout: LayoutConfig,
) -> None:
    """One control tick: perceive, advance journeys, assign new work."""
    if not state.started:
        _init(state, fleet, blueprint)

    obs = gt_observation(fleet[0])      # any GtSensor sees the whole world
    _eval_goals(state, obs, blueprint)
    for r in fleet:
        _advance(state, r)
    _PHASE_HANDLERS[state.phase](state, fleet, blueprint, layout, obs)
