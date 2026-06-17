from __future__ import annotations

import simpy

from ...sim.config import LayoutConfig
from ...mission.blueprint import Blueprint
from ...mission.goals import (
    AIRLOCK_DOCKED,
    ANCHORS,
    BLOCKS,
    POD_INFLATED,
    SITE_PREP,
    Goal,
)
from ...sim.robots import Assembler, Loader, Producer, Robot, RobotsConfig
from ...sim.sensors import GtObservation, GtSensor, SensorsConfig
from ...sim.world import World
from ..base import AutonomyState
from ..navigation import navigate
from ..perception import gt_observation


def _record(
    state: AutonomyState, obs: GtObservation, blueprint: Blueprint, goal: Goal
) -> tuple[bool, str]:
    ok, reason = goal.is_done(obs, blueprint)
    state.goal_status[goal.name] = (ok, reason)
    mark = "OK " if ok else "FAIL"
    print(f"[goal] {goal.name} {mark}: {reason}")
    return ok, reason


def spawn_fleet(
    world: World,
    config: RobotsConfig,
    layout: LayoutConfig,
    sensors: SensorsConfig,
) -> list[Robot]:
    """Build the fleet, giving each robot its world handle and a GtSensor."""

    def mount() -> list[GtSensor]:
        return [GtSensor(world, sensors.gt)]

    fleet: list[Robot] = []
    lx, ly = layout.loader_depot
    for i, loader_config in enumerate(config.loaders):
        fleet.append(Loader(f"L{i}", lx + i, ly, loader_config, world, mount()))
    for i, (producer_config, (px, py)) in enumerate(
        zip(config.producers, layout.producer_sites)
    ):
        fleet.append(Producer(f"P{i}", px, py, producer_config, world, mount()))
    ax, ay = layout.assembler_depot
    for i, assembler_config in enumerate(config.assemblers):
        fleet.append(Assembler(f"A{i}", ax - i, ay, assembler_config, world, mount()))
    return fleet


def fetch_and_place(
    env: simpy.Environment,
    asm: Assembler,
    source: tuple[int, int],
    target: tuple[int, int],
    item: str,
    place_time: float,
):
    """Navigate to `source`, pick up `item`, navigate to `target`, place it.

    Movement lives here (autonomy); the assembler only carries and places (the
    placement effect on the world is the robot's, keyed by the carried item).
    """
    yield env.process(navigate(env, asm, source))
    asm.pickup(item)
    yield env.process(navigate(env, asm, target))
    yield env.process(asm.place(env, target, place_time))


# ---------------------------------------------------------------------------
# Phase 1 — Site Preparation
# ---------------------------------------------------------------------------


def _loader_dig_loop(
    env: simpy.Environment,
    loader: Loader,
    targets: simpy.Store,
    done: simpy.Event,
    spoil_site: tuple[int, int],
):
    while True:
        if loader.regolith >= loader.config.loader_capacity:
            yield env.process(navigate(env, loader, spoil_site))
            yield env.process(loader.unload_ground(env, spoil_site))
            continue
        if not targets.items:
            if done.triggered:
                if loader.regolith > 0:
                    yield env.process(navigate(env, loader, spoil_site))
                    yield env.process(loader.unload_ground(env, spoil_site))
                return
            yield env.timeout(0.2)
            continue
        cell = yield targets.get()
        if not isinstance(cell, tuple):
            continue
        yield env.process(navigate(env, loader, cell))
        yield env.process(loader.excavate(env, cell))


def _loader_grade_loop(
    env: simpy.Environment,
    loader: Loader,
    targets: simpy.Store,
    done: simpy.Event,
):
    while True:
        if not targets.items:
            if done.triggered:
                return
            yield env.timeout(0.2)
            continue
        cell = yield targets.get()
        if not isinstance(cell, tuple):
            continue
        yield env.process(navigate(env, loader, cell))
        yield env.process(loader.grade(env, cell))


# ---------------------------------------------------------------------------
# Phase 2 — supply chain
# ---------------------------------------------------------------------------


def _nearest(cells: list[tuple[int, int]], pos: tuple[int, int]) -> tuple[int, int]:
    return min(cells, key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]))


def _loader_supply_loop(
    env: simpy.Environment,
    loader: Loader,
    producers: list[Producer],
    done: simpy.Event,
    regolith_pits: list[tuple[int, int]],
):
    while not done.triggered:
        pit = _nearest(regolith_pits, loader.pos)
        yield env.process(navigate(env, loader, pit))
        while loader.regolith < loader.config.loader_capacity and not done.triggered:
            yield env.process(loader.excavate(env, pit))
        if done.triggered:
            break
        target = min(producers, key=lambda p: p.regolith_inventory)
        yield env.process(navigate(env, loader, target.pos))
        yield env.process(loader.unload_into(env, target))


def _assembler_anchor_loop(
    env: simpy.Environment,
    assembler: Assembler,
    queue: simpy.Store,
    done: simpy.Event,
    assembler_depot: tuple[int, int],
):
    while True:
        if not queue.items:
            if done.triggered:
                return
            yield env.timeout(0.2)
            continue
        cell = yield queue.get()
        if not isinstance(cell, tuple):
            continue
        yield env.process(
            fetch_and_place(
                env,
                assembler,
                assembler_depot,
                cell,
                "anchor",
                assembler.config.anchor_drive_time,
            )
        )


def _assembler_block_loop(
    env: simpy.Environment,
    assembler: Assembler,
    block_store: simpy.Store,
    placements: simpy.Store,
    done: simpy.Event,
):
    while True:
        if not placements.items:
            if done.triggered:
                return
            yield env.timeout(0.2)
            continue
        target = yield placements.get()
        if not isinstance(target, tuple):
            continue
        source = yield block_store.get()
        if not isinstance(source, tuple):
            continue
        yield env.process(
            fetch_and_place(
                env,
                assembler,
                source,
                target,
                "block",
                assembler.config.block_place_time,
            )
        )


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


def run_mission(
    env: simpy.Environment,
    fleet: list[Robot],
    state: AutonomyState,
    blueprint: Blueprint,
    layout: LayoutConfig,
):
    loaders = [r for r in fleet if isinstance(r, Loader)]
    producers = [r for r in fleet if isinstance(r, Producer)]
    assemblers = [r for r in fleet if isinstance(r, Assembler)]

    # Start every mounted sensor publishing at its rate. The autonomy only ever
    # perceives the world through these (via `gt_observation`), never directly.
    for r in fleet:
        for s in r.sensors:
            env.process(s.run(env))

    # A representative robot whose GtSensor backs global/grid reads (goal checks,
    # placed-component counts). Any robot's GtSensor sees everything.
    eye = fleet[0]

    # ---- Site prep: dig, then grade --------------------------------------
    state.current_activity = "Site Prep — Dig"
    foundation = list(blueprint.foundation_cells(gt_observation(eye)))

    dig_targets = simpy.Store(env)
    for cell in foundation:
        yield dig_targets.put(cell)
    dig_done = env.event()
    for ld in loaders:
        env.process(
            _loader_dig_loop(env, ld, dig_targets, dig_done, layout.spoil_site)
        )
    while dig_targets.items or any(ld.state != "idle" for ld in loaders):
        yield env.timeout(1.0)
    dig_done.succeed()
    yield env.timeout(0.5)

    for attempt in range(5):
        state.current_activity = f"Site Prep — Grade (pass {attempt + 1})"
        grade_targets = simpy.Store(env)
        for cell in foundation:
            yield grade_targets.put(cell)
        grade_done = env.event()
        for ld in loaders:
            env.process(_loader_grade_loop(env, ld, grade_targets, grade_done))
        while grade_targets.items or any(ld.state != "idle" for ld in loaders):
            yield env.timeout(1.0)
        grade_done.succeed()
        if _record(state, gt_observation(eye), blueprint, SITE_PREP)[0]:
            break
    yield env.timeout(1.0)

    # ---- Anchors ---------------------------------------------------------
    state.current_activity = "Placing anchors"
    anchor_queue = simpy.Store(env)
    for cell in blueprint.anchor_cells():
        yield anchor_queue.put(cell)
    anchors_done = env.event()

    for a in assemblers:
        env.process(
            _assembler_anchor_loop(
                env, a, anchor_queue, anchors_done, layout.assembler_depot
            )
        )
    while len(gt_observation(eye).anchors) < blueprint.config.num_anchors:
        yield env.timeout(1.0)
    anchors_done.succeed()
    _record(state, gt_observation(eye), blueprint, ANCHORS)

    # ---- Blocks ----------------------------------------------------------
    state.current_activity = "Producing blocks"
    block_store = simpy.Store(env)
    placements = simpy.Store(env)
    target_blocks = blueprint.dome_floor_cells()
    for cell in target_blocks:
        yield placements.put(cell)
    stop_production = env.event()
    build_done = env.event()

    for p in producers:
        env.process(p.run(env, block_store, stop_production))
    for ld in loaders:
        env.process(
            _loader_supply_loop(
                env, ld, producers, stop_production, layout.regolith_pits
            )
        )
    for a in assemblers:
        env.process(_assembler_block_loop(env, a, block_store, placements, build_done))

    while len(gt_observation(eye).blocks) < len(target_blocks):
        yield env.timeout(1.0)
    build_done.succeed()
    stop_production.succeed()
    yield env.timeout(1.0)
    _record(state, gt_observation(eye), blueprint, BLOCKS)

    # ---- Airlock ---------------------------------------------------------
    state.current_activity = "Docking airlock"
    docker = assemblers[0]
    yield env.process(
        fetch_and_place(
            env,
            docker,
            layout.assembler_depot,
            blueprint.airlock_cell(),
            "airlock",
            docker.config.dock_time,
        )
    )
    # Wait until the sensor reports the dock before concluding (publish latency).
    while not gt_observation(eye).airlock_docked:
        yield env.timeout(0.2)
    _record(state, gt_observation(eye), blueprint, AIRLOCK_DOCKED)

    # ---- Pod inflation ---------------------------------------------------
    state.current_activity = "Inflating pod"
    yield env.process(docker.inflate_pod(env, docker.config.inflate_time))
    while gt_observation(eye).pod_inflation < 0.999:
        yield env.timeout(0.2)
    _record(state, gt_observation(eye), blueprint, POD_INFLATED)

    state.current_activity = "Mission complete"
    state.finish_time = env.now
