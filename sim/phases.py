from __future__ import annotations

import simpy

from . import blueprint
from .config import (
    ASSEMBLER_DEPOT,
    CONFIG,
    LOADER_DEPOT,
    PRODUCER_SITES,
    REGOLITH_PITS,
)
from .robots import Assembler, Loader, Producer, Robot
from .world import World


def spawn_fleet(world: World) -> list[Robot]:
    fleet: list[Robot] = []
    lx, ly = LOADER_DEPOT
    for i in range(CONFIG.num_loaders):
        fleet.append(Loader(f"L{i}", lx + i, ly))
    for i, (px, py) in enumerate(PRODUCER_SITES[: CONFIG.num_producers]):
        fleet.append(Producer(f"P{i}", px, py))
    ax, ay = ASSEMBLER_DEPOT
    for i in range(CONFIG.num_assemblers):
        fleet.append(Assembler(f"A{i}", ax - i, ay))
    return fleet


# ---------------------------------------------------------------------------
# Phase 1 — Site Preparation
# ---------------------------------------------------------------------------


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
        while loader.regolith < CONFIG.loader_capacity and not done.triggered:
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
                CONFIG.anchor_drive_time,
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
                CONFIG.block_place_time,
                world.set_block,
            )
        )


def _set_airlock(world: World, x: int, y: int) -> None:
    world.airlock_docked = True
    world.pod_deployed = True


# ---------------------------------------------------------------------------
# Mission
# ---------------------------------------------------------------------------


def run_mission(env: simpy.Environment, world: World, fleet: list[Robot]):
    loaders = [r for r in fleet if isinstance(r, Loader)]
    producers = [r for r in fleet if isinstance(r, Producer)]
    assemblers = [r for r in fleet if isinstance(r, Assembler)]

    # ---- Phase 1: grading -------------------------------------------------
    world.phase = 1
    world.phase_label = "Site Preparation"
    targets = simpy.Store(env)
    phase1_done = env.event()

    foundation = [
        c
        for c in world.foundation_cells()
        if abs(world.elevation[c[1]][c[0]]) > CONFIG.elevation_tolerance_cm
    ]
    for cell in foundation:
        yield targets.put(cell)

    for ld in loaders:
        env.process(_loader_grade_loop(env, world, ld, targets, phase1_done))

    while targets.items or any(ld.state != "idle" for ld in loaders):
        yield env.timeout(1.0)
    phase1_done.succeed()
    yield env.timeout(1.0)

    # ---- Phase 2: protective shell ---------------------------------------
    world.phase = 2
    world.phase_label = "Protective Shell"

    # 2a — anchors first (assemblers fetch from depot)
    anchor_queue = simpy.Store(env)
    for cell in blueprint.anchor_cells():
        yield anchor_queue.put(cell)
    anchors_done = env.event()

    for a in assemblers:
        env.process(_assembler_anchor_loop(env, world, a, anchor_queue, anchors_done))
    while len(world.anchors) < CONFIG.num_anchors:
        yield env.timeout(1.0)
    anchors_done.succeed()

    # 2b — block production: loaders → producers → assemblers
    block_store = simpy.Store(env)
    placements = simpy.Store(env)
    target_blocks = blueprint.dome_ring_cells()
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

    # ---- Phase 3: deployment & docking -----------------------------------
    world.phase = 3
    world.phase_label = "Deployment & Docking"
    docker = assemblers[0]
    yield env.process(
        docker.fetch_and_place(
            env,
            world,
            ASSEMBLER_DEPOT,
            blueprint.airlock_cell(),
            "airlock",
            CONFIG.dock_time,
            lambda x, y: _set_airlock(world, x, y),
        )
    )

    world.phase = 4
    world.phase_label = "Mission complete"
    world.finish_time = env.now
