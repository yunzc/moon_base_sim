"""moon_base_sim entry point.

Runs the SimPy mission alongside a Pygame top-down view. The SimPy clock is
advanced in small steps between frames, so the visualization stays responsive
while long processing times (produce/grade/place) still "fast-forward".
"""
from __future__ import annotations

import argparse
import sys

import simpy

from .autonomy import AutonomyState, load_autonomy
from .mission.blueprint import Blueprint
from .mission.goals import GOALS
from .sim.config import CONFIG
from .sim.world import World


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-time", type=float, default=10_000.0)
    p.add_argument("--autonomy", default="baseline")
    return p.parse_args()


def _mission_done(state: AutonomyState) -> bool:
    return all(state.goal_status.get(g.name, (False, ""))[0] for g in GOALS)


def _goals_done(state: AutonomyState) -> int:
    return sum(1 for g in GOALS if state.goal_status.get(g.name, (False, ""))[0])


def run_headless(autonomy_name: str, seed: int, max_time: float) -> int:
    env = simpy.Environment()
    world = World.generate(seed=seed)
    blueprint = Blueprint()
    autonomy = load_autonomy(autonomy_name)
    fleet = autonomy.spawn_fleet(world)
    env.process(autonomy.run(env, world, fleet, blueprint))
    env.run(until=max_time)
    state = autonomy.state
    print(
        f"activity={state.current_activity!r} "
        f"anchors={len(world.anchors)} blocks={len(world.blocks)} "
        f"docked={world.airlock_docked} "
        f"goals_done={_goals_done(state)}/{len(GOALS)} "
        f"finished_at={state.finish_time:.1f}s"
    )
    return 0 if _mission_done(state) else 1


def run_visual(autonomy_name: str, seed: int) -> int:
    autonomy = load_autonomy(autonomy_name)
    from .viz.render import Renderer

    env = simpy.Environment()
    world = World.generate(seed=seed)
    blueprint = Blueprint()
    fleet = autonomy.spawn_fleet(world)
    env.process(autonomy.run(env, world, fleet, blueprint))
    renderer = Renderer(world, fleet, autonomy, blueprint)

    step = CONFIG.sim_speed / CONFIG.target_fps
    running = True
    while running:
        try:
            env.run(until=env.now + step)
        except Exception as exc:
            print(f"sim error: {exc}", file=sys.stderr)
            break
        running = renderer.draw(env.now)
        if _mission_done(autonomy.state):
            while renderer.draw(env.now):
                pass
            break
    return 0


def main() -> None:
    args = parse_args()
    if args.headless:
        raise SystemExit(run_headless(args.autonomy, args.seed, args.max_time))
    raise SystemExit(run_visual(args.autonomy, args.seed))


if __name__ == "__main__":
    main()
