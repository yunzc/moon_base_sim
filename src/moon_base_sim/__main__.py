"""moon_base_sim sim service.

Runs the world + fleet as a real-time zmq service: robots publish telemetry and
consume commands, an autonomy connects separately (``python -m
moon_base_sim.autonomy``). The sim runs free whether or not a client is attached.
"""
from __future__ import annotations

import argparse
import sys

from .mission.blueprint import Blueprint
from .mission.goals import GOALS, all_complete, latched_statuses
from .sim.config import Config, load_config
from .sim.simulator import Simulator


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="path to a config YAML file")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--max-time", type=float, default=1e9, help="stop after N sim-seconds")
    p.add_argument("--telemetry", help="override comms.telemetry_addr")
    p.add_argument("--commands", help="override comms.command_addr")
    p.add_argument("--factor", type=float, help="override comms.factor (wall-s per sim-s)")
    return p.parse_args()


def _with_comms_overrides(config: Config, telemetry, commands, factor) -> Config:
    updates = {}
    if telemetry:
        updates["telemetry_addr"] = telemetry
    if commands:
        updates["command_addr"] = commands
    if factor is not None:
        updates["factor"] = factor
    if not updates:
        return config
    return config.model_copy(update={"comms": config.comms.model_copy(update=updates)})


def _summary(world, statuses, now: float) -> None:
    done = sum(1 for ok, _ in statuses.values() if ok)
    print(
        f"anchors={len(world.anchors)} blocks={len(world.blocks)} "
        f"docked={world.airlock_docked} goals_done={done}/{len(GOALS)} t={now:.1f}s"
    )


def run(config: Config, headless: bool, seed: int, max_time: float) -> int:
    sim = Simulator(config, seed=seed)
    blueprint = Blueprint(config.blueprint)
    latched: dict = {}

    renderer = None
    if headless:
        chunk = 0.2
    else:
        from .viz.render import Renderer

        renderer = Renderer(sim.world, sim.fleet, blueprint, config.sim)
        chunk = (1.0 / config.sim.target_fps) / config.comms.factor

    print(
        f"sim listening — telemetry {config.comms.telemetry_addr}  "
        f"commands {config.comms.command_addr}"
    )
    running = True
    done = False
    while running and sim.now < max_time:
        try:
            sim.step(chunk)
        except Exception as exc:
            print(f"sim error: {exc}", file=sys.stderr)
            break
        sim.route(sim.endpoint.poll_commands())
        statuses = latched_statuses(sim.world, blueprint, latched)
        if renderer is not None:
            running = renderer.draw(sim.now)
        if all_complete(statuses) and not done:
            done = True
            print("mission complete:")
            _summary(sim.world, statuses, sim.now)
            # Keep running/publishing so connected clients can observe completion
            # too; the service stops on --max-time or Ctrl-C.

    _summary(sim.world, latched_statuses(sim.world, blueprint, latched), sim.now)
    return 0


def main() -> None:
    args = parse_args()
    config = _with_comms_overrides(
        load_config(args.config), args.telemetry, args.commands, args.factor
    )
    raise SystemExit(run(config, args.headless, args.seed, args.max_time))


if __name__ == "__main__":
    main()
