"""moon_base_sim entry point.

Runs the SimPy mission alongside a Pygame top-down view. The SimPy clock is
advanced in small steps between frames, so the visualization stays responsive
while long processing times (produce/grade/place) still "fast-forward".
"""
from __future__ import annotations

import argparse
import sys

import simpy

from sim.config import CONFIG
from sim.phases import run_mission, spawn_fleet
from sim.world import World


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-time", type=float, default=10_000.0)
    return p.parse_args()


def run_headless(seed: int, max_time: float) -> int:
    env = simpy.Environment()
    world = World.generate(seed=seed)
    fleet = spawn_fleet(world)
    env.process(run_mission(env, world, fleet))
    env.run(until=max_time)
    print(
        f"phase={world.phase} label={world.phase_label!r} "
        f"anchors={len(world.anchors)} blocks={len(world.blocks)} "
        f"docked={world.airlock_docked} finished_at={world.finish_time:.1f}s"
    )
    return 0 if world.phase >= 4 else 1


def run_visual(seed: int) -> int:
    from viz.render import Renderer

    env = simpy.Environment()
    world = World.generate(seed=seed)
    fleet = spawn_fleet(world)
    env.process(run_mission(env, world, fleet))
    renderer = Renderer(world, fleet)

    step = CONFIG.sim_speed / CONFIG.target_fps
    running = True
    while running:
        try:
            env.run(until=env.now + step)
        except Exception as exc:
            print(f"sim error: {exc}", file=sys.stderr)
            break
        running = renderer.draw(env.now)
        if world.phase >= 4:
            while renderer.draw(env.now):
                pass
            break
    return 0


def main() -> int:
    args = parse_args()
    if args.headless:
        return run_headless(args.seed, args.max_time)
    return run_visual(args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
