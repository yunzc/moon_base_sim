#!/bin/bash
# Test script to run sim and autonomy together

echo "Starting simulator in background (headless mode, 10 second timeout)..."
uv run python -m moon_base_sim --sim configs/sim.yaml --fleet configs/fleet.yaml \
    --blueprint configs/blueprint.yaml --comms configs/comms.yaml \
    --headless --max-time 10 &
SIM_PID=$!

sleep 2

echo "Starting autonomy..."
timeout 5 uv run python -m moon_base_sim.autonomy --fleet configs/fleet.yaml \
    --blueprint configs/blueprint.yaml --comms configs/comms.yaml &
AUTONOMY_PID=$!

wait $AUTONOMY_PID
wait $SIM_PID

echo "Test complete"