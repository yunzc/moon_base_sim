#!/usr/bin/env python3
"""Test visualization status display by sending commands directly to robots."""

import sys
sys.path.insert(0, 'src')

from moon_base_sim.sim.config import load_config
from moon_base_sim.sim.simulator import Simulator
from moon_base_sim.comms.messages import Command
from moon_base_sim.viz.render import Renderer
from moon_base_sim.mission.blueprint import Blueprint
import pygame
import time

# Load config
config = load_config("configs/sim.yaml", "configs/fleet.yaml", "configs/blueprint.yaml", "configs/comms.yaml")

# Create simulator
sim = Simulator(config, seed=0)
blueprint = Blueprint(config.blueprint)

# Create renderer
renderer = Renderer(sim.world, sim.fleet, blueprint, config.sim)

# Send some test commands to robots
commands = [
    Command("L0", 1, "step", ("right",)),
    Command("L1", 1, "excavate", ((5, 5),)),
    Command("A0", 1, "step", ("up",)),
]

for cmd in commands:
    robot = next((r for r in sim.fleet if r.rid == cmd.rid), None)
    if robot:
        robot.deliver(cmd)
        print(f"Sent command to {cmd.rid}: {cmd.verb}")

# Run visualization loop for a few seconds
print("\nRunning visualization (press ESC to exit)...")
start_time = time.time()
running = True

while running and (time.time() - start_time < 10):
    # Step simulation
    sim.step(0.05)

    # Draw and check for quit
    running = renderer.draw(sim.now)

    # Print current robot states
    if int(time.time() - start_time) % 2 == 0:  # Every 2 seconds
        print(f"\nTime: {sim.now:.1f}s")
        for r in sim.fleet[:3]:  # Just show first 3 robots
            print(f"  {r.rid}: state={r.state}, busy={r._busy}")

pygame.quit()
print("\nVisualization test complete")