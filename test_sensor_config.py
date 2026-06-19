#!/usr/bin/env python3
"""Test if sensor configs are loading correctly."""

import sys
sys.path.insert(0, 'src')

from moon_base_sim.sim.config import load_config

# Load config
config = load_config("configs/sim.yaml", "configs/fleet.yaml", "configs/blueprint.yaml", "configs/comms.yaml")

# Check robot configs
print("Robot sensor configs:")
for i, loader_config in enumerate(config.robots.loaders):
    print(f"  Loader {i}:")
    print(f"    Has sensors attr: {hasattr(loader_config, 'sensors')}")
    if hasattr(loader_config, 'sensors'):
        print(f"    Has gt sensor: {hasattr(loader_config.sensors, 'gt')}")
        if hasattr(loader_config.sensors, 'gt'):
            print(f"    GT publish_hz: {loader_config.sensors.gt.publish_hz}")