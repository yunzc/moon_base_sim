from __future__ import annotations

import simpy

from ...sim.config import (
    ASSEMBLER_DEPOT,
    CONFIG,
    LOADER_DEPOT,
    PRODUCER_SITES,
    REGOLITH_PITS,
    SPOIL_SITE,
)
from ...mission.blueprint import Blueprint
from ...mission.goals import (
    AIRLOCK_DOCKED,
    ANCHORS,
    BLOCKS,
    POD_INFLATED,
    SITE_PREP,
    Goal,
)
from ...sim.robots import Assembler, Loader, Producer, Robot, RobotConfig
from ...sim.world import World
from ..base import AutonomyState


def _record(
    state: AutonomyState, world: World, blueprint: Blueprint, goal: Goal
) -> tuple[bool, str]:
    ok, reason = goal.is_done(world, blueprint)
    state.goal_status[goal.name] = (ok, reason)
    mark = "OK " if ok else "FAIL"
    print(f"[goal] {goal.name} {mark}: {reason}")
    return ok, reason


def spawn_fleet(world: World, config: RobotConfig | None = None) -> list[Robot]:
    config = config or RobotConfig()
    fleet: list[Robot] = []
    lx, ly = LOADER_DEPOT
    for i in range(config.num_loaders):
        fleet.append(Loader(f"L{i}", lx + i, ly, config))
    for i, (px, py) in enumerate(PRODUCER_SITES[: config.num_producers]):
        fleet.append(Producer(f"P{i}", px, py, config))
    ax, ay = ASSEMBLER_DEPOT
    for i in range(config.num_assemblers):
        fleet.append(Assembler(f"A{i}", ax - i, ay, config))
    return fleet


# ---------------------------------------------------------------------------
# Phase 1 — Site Preparation
# ---------------------------------------------------------------------------


def _loader_dig_loop(
    env: simpy.Environment,
    world: World,
    loader: Loader,
    targets: simpy.Store,
    done: simpy.Event,
):
    while True:
        if loader.regolith >= loader.config.loader_capacity:
            yield env.process(loader.unload_ground(env, world, SPOIL_SITE))
            continue
        if not targets.items:
            if done.triggered:
                if loader.regolith > 0:
                    yield env.process(loader.unload_ground(env, world, SPOIL_SITE))
                return
            yield env.timeout(0.2)
            continue
        cell = yield targets.get()
        if not isinstance(cell, tuple):
            continue
        yield env.process(loader.excavate(env, world, cell))


def _loader_grade_loop(
    env: simpy.Environment,
    world: World,
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
        yield env.process(loader.grade(env, world, cell))


# ---------------------------------------------------------------------------
# Phase 2 — supply chain
# ---------------------------------------------------------------------------


def _nearest(cells: list[tuple[int, int]], pos: tuple[int, int]) -> tuple[int, int]:
    return min(cells, key=lambda c: abs(c[0] - pos[0]) + abs(c[1] - pos[1]))


def _loader_supply_loop(
    env: simpy.Environment,
    world: World,
    loader: Loader,
    producers: list[Producer],
    done: simpy.Event,
):
    while not done.triggered:
        pit = _nearest(REGOLITH_PITS, loader.pos)
        while loader.regolith < loader.config.loader_capacity and not done.triggered:
            yield env.process(loader.excavate(env, world, pit))
        if done.triggered:
            break
        target = min(producers, key=lambda p: p.regolith_inventory)
        yield env.process(loader.unload_into(env, world, target))


def _assembler_anchor_loop(
    env: simpy.Environment,
    world: World,
    assembler: Assembler,
    queue: simpy.Store,
    done: simpy.Event,
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
            assembler.fetch_and_place(
                env,
                world,
                ASSEMBLER_DEPOT,
                cell,
                "anchor",
                assembler.config.anchor_drive_time,
                world.set_anchor,
            )
        )


def _assembler_block_loop(
    env: simpy.Environment,
    world: World,
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
            assembler.fetch_and_place(
                env,
                world,
                source,
                target,
                "block",
                assembler.config.block_place_time,
                world.set_block,
            )
        )


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


def run_mission(
    env: simpy.Environment,
    world: World,
    fleet: list[Robot],
    state: AutonomyState,
    blueprint: Blueprint,
):
    loaders = [r for r in fleet if isinstance(r, Loader)]
    producers = [r for r in fleet if isinstance(r, Producer)]
    assemblers = [r for r in fleet if isinstance(r, Assembler)]

    # ---- Site prep: dig, then grade --------------------------------------
    state.current_activity = "Site Prep — Dig"
    foundation = list(blueprint.foundation_cells(world))

    dig_targets = simpy.Store(env)
    for cell in foundation:
        yield dig_targets.put(cell)
    dig_done = env.event()
    for ld in loaders:
        env.process(_loader_dig_loop(env, world, ld, dig_targets, dig_done))
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
            env.process(_loader_grade_loop(env, world, ld, grade_targets, grade_done))
        while grade_targets.items or any(ld.state != "idle" for ld in loaders):
            yield env.timeout(1.0)
        grade_done.succeed()
        if _record(state, world, blueprint, SITE_PREP)[0]:
            break
    yield env.timeout(1.0)

    # ---- Anchors ---------------------------------------------------------
    state.current_activity = "Placing anchors"
    anchor_queue = simpy.Store(env)
    for cell in blueprint.anchor_cells():
        yield anchor_queue.put(cell)
    anchors_done = env.event()

    for a in assemblers:
        env.process(_assembler_anchor_loop(env, world, a, anchor_queue, anchors_done))
    while len(world.anchors) < CONFIG.num_anchors:
        yield env.timeout(1.0)
    anchors_done.succeed()
    _record(state, world, blueprint, ANCHORS)

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
        env.process(p.run(env, world, block_store, stop_production))
    for ld in loaders:
        env.process(_loader_supply_loop(env, world, ld, producers, stop_production))
    for a in assemblers:
        env.process(
            _assembler_block_loop(
                env, world, a, block_store, placements, build_done
            )
        )

    while len(world.blocks) < len(target_blocks):
        yield env.timeout(1.0)
    build_done.succeed()
    stop_production.succeed()
    yield env.timeout(1.0)
    _record(state, world, blueprint, BLOCKS)

    # ---- Airlock ---------------------------------------------------------
    state.current_activity = "Docking airlock"
    docker = assemblers[0]
    yield env.process(
        docker.dock_airlock(env, world, ASSEMBLER_DEPOT, blueprint.airlock_cell())
    )
    _record(state, world, blueprint, AIRLOCK_DOCKED)

    # ---- Pod inflation ---------------------------------------------------
    state.current_activity = "Inflating pod"
    yield env.process(docker.inflate_pod(env, world, docker.config.inflate_time))
    _record(state, world, blueprint, POD_INFLATED)

    state.current_activity = "Mission complete"
    state.finish_time = env.now
