from __future__ import annotations

import simpy

from . import blueprint
from .config import ASSEMBLER_DEPOT, CONFIG, LOADER_DEPOT, PRODUCER_SITES
from .robots import (
    Robot,
    assembler_anchor,
    assembler_build,
    docker_process,
    loader_grade,
    producer_loop,
)
from .world import World


LOADER_COLOR = (240, 180, 60)
PRODUCER_COLOR = (120, 200, 240)
ASSEMBLER_COLOR = (220, 120, 220)


def spawn_fleet(world: World) -> list[Robot]:
    fleet: list[Robot] = []
    lx, ly = LOADER_DEPOT
    for i in range(CONFIG.num_loaders):
        fleet.append(Robot(f"L{i}", "loader", lx + i, ly, LOADER_COLOR))
    for i, (px, py) in enumerate(PRODUCER_SITES[: CONFIG.num_producers]):
        fleet.append(Robot(f"P{i}", "producer", px, py, PRODUCER_COLOR))
    ax, ay = ASSEMBLER_DEPOT
    for i in range(CONFIG.num_assemblers):
        fleet.append(Robot(f"A{i}", "assembler", ax - i, ay, ASSEMBLER_COLOR))
    return fleet


def run_mission(env: simpy.Environment, world: World, fleet: list[Robot]):
    loaders = [r for r in fleet if r.kind == "loader"]
    producers = [r for r in fleet if r.kind == "producer"]
    assemblers = [r for r in fleet if r.kind == "assembler"]

    # ---- Phase 1 ----------------------------------------------------------
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

    for loader in loaders:
        env.process(loader_grade(env, world, loader, targets, phase1_done))

    while targets.items or any(r.state != "idle" for r in loaders):
        yield env.timeout(1.0)
    phase1_done.succeed()
    yield env.timeout(1.0)

    # ---- Phase 2 ----------------------------------------------------------
    world.phase = 2
    world.phase_label = "Protective Shell"

    anchor_queue = simpy.Store(env)
    for cell in blueprint.anchor_cells():
        yield anchor_queue.put(cell)
    anchors_done = env.event()

    anchor_procs = [
        env.process(assembler_anchor(env, world, a, anchor_queue, anchors_done))
        for a in assemblers
    ]
    while len(world.anchors) < CONFIG.num_anchors:
        yield env.timeout(1.0)
    anchors_done.succeed()

    block_store = simpy.Store(env)
    placements = simpy.Store(env)
    target_blocks = blueprint.dome_ring_cells()
    for cell in target_blocks:
        yield placements.put(cell)
    stop_production = env.event()
    build_done = env.event()

    for p in producers:
        env.process(producer_loop(env, world, p, block_store, stop_production))
    for a in assemblers:
        env.process(assembler_build(env, world, a, block_store, placements, build_done))

    while len(world.blocks) < len(target_blocks):
        yield env.timeout(1.0)
    build_done.succeed()
    stop_production.succeed()
    yield env.timeout(1.0)

    # ---- Phase 3 ----------------------------------------------------------
    world.phase = 3
    world.phase_label = "Deployment & Docking"
    docker = assemblers[0]
    yield env.process(docker_process(env, world, docker, blueprint.airlock_cell()))

    world.phase = 4
    world.phase_label = "Mission complete"
    world.finish_time = env.now
