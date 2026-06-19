#!/usr/bin/env python3
"""Test script to verify robot status updates."""

import sys
import time
sys.path.insert(0, 'src')

from moon_base_sim.sim.config import load_config
from moon_base_sim.sim.simulator import Simulator
from moon_base_sim.comms.messages import Command

# Load config
config = load_config("configs/sim.yaml", "configs/fleet.yaml", "configs/blueprint.yaml", "configs/comms.yaml")

# Create simulator
sim = Simulator(config, seed=0)

# Print initial states
print("\nInitial robot states:")
for r in sim.fleet:
    print(f"  {r.rid}: state={r.state}, is_idle={r.is_idle}, _busy={r._busy}")

# Send a command to a loader
if sim.fleet:
    robot = sim.fleet[0]
    cmd = Command(robot.rid, 1, "step", ("right",))
    robot.deliver(cmd)

    # Step simulation
    sim.step(0.1)

    print(f"\nAfter sending 'step' command to {robot.rid}:")
    for r in sim.fleet:
        print(f"  {r.rid}: state={r.state}, is_idle={r.is_idle}, _busy={r._busy}")

    # Step more to let command complete
    sim.step(2.0)

    print(f"\nAfter waiting for command to complete:")
    for r in sim.fleet:
        print(f"  {r.rid}: state={r.state}, is_idle={r.is_idle}, _busy={r._busy}")