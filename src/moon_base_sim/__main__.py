"""moon_base_sim entry point.

The rollout loop builds a :class:`Simulator` and an autonomy, then interleaves
``autonomy.decide(...)`` with ``sim.step(dt)`` (per-frame steps in the visual path).
"""
from __future__ import annotations

import argparse
import sys

from .autonomy import AutonomyState, load_autonomy
from .mission.blueprint import Blueprint
from .mission.goals import GOALS
from .sim.config import Config, load_config
from .sim.simulator import Simulator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="path to a config YAML file")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-time", type=float, default=10_000.0)
    p.add_argument("--autonomy", default="baseline")
    return p.parse_args()


def _mission_done(state: AutonomyState) -> bool:
    return all(state.goal_status.get(g.name, (False, ""))[0] for g in GOALS)


def _goals_done(state: AutonomyState) -> int:
    return sum(1 for g in GOALS if state.goal_status.get(g.name, (False, ""))[0])


def run_headless(
    config: Config, autonomy_name: str, seed: int, max_time: float
) -> int:
    sim = Simulator(config, seed=seed)
    blueprint = Blueprint(config.blueprint)
    autonomy = load_autonomy(autonomy_name, config)

    while sim.now < max_time and not _mission_done(autonomy.state):
        autonomy.decide(sim.fleet, blueprint)
        sim.step(config.sim.tick)
    if _mission_done(autonomy.state):
        autonomy.state.finish_time = sim.now

    state = autonomy.state
    world = sim.world
    print(
        f"activity={state.current_activity!r} "
        f"anchors={len(world.anchors)} blocks={len(world.blocks)} "
        f"docked={world.airlock_docked} "
        f"goals_done={_goals_done(state)}/{len(GOALS)} "
        f"finished_at={state.finish_time:.1f}s"
    )
    return 0 if _mission_done(state) else 1


def run_visual(config: Config, autonomy_name: str, seed: int) -> int:
    autonomy = load_autonomy(autonomy_name, config)
    from .viz.render import Renderer

    sim = Simulator(config, seed=seed)
    blueprint = Blueprint(config.blueprint)
    renderer = Renderer(sim.world, sim.fleet, blueprint, config.sim)

    step = config.sim.sim_speed / config.sim.target_fps
    running = True
    while running:
        try:
            autonomy.decide(sim.fleet, blueprint)
            sim.step(step)
        except Exception as exc:
            print(f"sim error: {exc}", file=sys.stderr)
            break
        running = renderer.draw(sim.now)
        if _mission_done(autonomy.state):
            autonomy.state.finish_time = sim.now
            while renderer.draw(sim.now):
                pass
            break
    return 0


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    if args.headless:
        raise SystemExit(
            run_headless(config, args.autonomy, args.seed, args.max_time)
        )
    raise SystemExit(run_visual(config, args.autonomy, args.seed))


if __name__ == "__main__":
    main()
