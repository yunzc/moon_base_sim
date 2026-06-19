"""Autonomy client: connect to a running sim service and drive it over zmq.

    uv run python -m moon_base_sim.autonomy --fleet configs/fleet.yaml --blueprint configs/blueprint.yaml
"""
from __future__ import annotations

import argparse

from ..comms import AutonomyEndpoint
from . import load_autonomy
from .client import run


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--fleet", required=True, help="path to fleet/layout config YAML file")
    p.add_argument("--blueprint", required=True, help="path to blueprint/goals config YAML file")
    p.add_argument("--comms", help="path to communication config YAML file (optional)")
    p.add_argument("--autonomy", default="baseline", help="autonomy type (default: baseline)")
    p.add_argument("--autonomy-config", help="path to autonomy-specific config YAML file (optional)")
    p.add_argument("--telemetry", help="telemetry address (default: tcp://127.0.0.1:5555)")
    p.add_argument("--commands", help="commands address (default: tcp://127.0.0.1:5556)")
    args = p.parse_args()

    # Load fleet and blueprint configs - these are what autonomy needs
    import yaml
    from pydantic import BaseModel, ConfigDict
    from ..mission.blueprint import BlueprintConfig
    from ..sim.robots import RobotsConfig
    from ..sim.config import LayoutConfig

    # Create a minimal config that contains only what autonomy needs
    class AutonomyConfig(BaseModel):
        model_config = ConfigDict(frozen=True)
        blueprint: BlueprintConfig
        robots: RobotsConfig
        layout: LayoutConfig

    # Load and merge the configs
    data = {}
    with open(args.fleet) as f:
        data.update(yaml.safe_load(f))
    with open(args.blueprint) as f:
        data.update(yaml.safe_load(f))

    config = AutonomyConfig.model_validate(data)

    # Load comms config if provided, otherwise use defaults
    telemetry = args.telemetry or "tcp://127.0.0.1:5555"
    commands = args.commands or "tcp://127.0.0.1:5556"
    if args.comms:
        with open(args.comms) as f:
            comms_data = yaml.safe_load(f)
            if "comms" in comms_data:
                telemetry = args.telemetry or comms_data["comms"].get("telemetry_addr", telemetry)
                commands = args.commands or comms_data["comms"].get("command_addr", commands)

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
