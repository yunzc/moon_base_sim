"""Autonomy client: connect to a running sim service and drive it over zmq.

    uv run python -m moon_base_sim.autonomy --config configs/default.yaml
"""
from __future__ import annotations

import argparse

from ..comms import AutonomyEndpoint
from ..sim.config import load_config
from . import load_autonomy
from .client import run


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True, help="path to a config YAML file")
    p.add_argument("--autonomy", default="baseline")
    p.add_argument("--telemetry", help="override comms.telemetry_addr")
    p.add_argument("--commands", help="override comms.command_addr")
    args = p.parse_args()

    config = load_config(args.config)
    telemetry = args.telemetry or config.comms.telemetry_addr
    commands = args.commands or config.comms.command_addr
    endpoint = AutonomyEndpoint(telemetry, commands)
    policy = load_autonomy(args.autonomy, config)
    print(f"autonomy '{args.autonomy}' — SUB {telemetry}  PUSH {commands}")
    try:
        run(policy, endpoint)
        print("mission complete")
    finally:
        endpoint.close()


if __name__ == "__main__":
    main()
