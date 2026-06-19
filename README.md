# moon_base_sim

A discrete-event simulation of automated lunar base construction: a fleet of
robots excavates terrain, sinters regolith into blocks, and assembles a shielded
habitat — all on a top-down grid, advanced by a SimPy clock and watchable through
a Pygame view.

The **sim** runs as a standalone service; an **autonomy** is a separate process that
connects over zmq to drive the fleet (see §3 Running and §4 Build your own autonomy).
This document covers the **simulator** (the world the robots live in), the **mission
spec** (blueprint geometry and the goals that define "done"), and the **pub/sub
contract** an autonomy talks to.

---

## 1. The Simulator

The simulator is a self-contained world: terrain, a fleet of robots, the sensors
mounted on them, and a clock. It exposes the robots' command APIs and advances
time on request; it makes no decisions of its own.

### `Simulator` (`sim/simulator.py`)

The container that owns everything:

* the **clock** — a SimPy `Environment` (the only place simulated time lives),
* the **world** — terrain + placed components,
* the **fleet** — robots, each with its mounted sensors.

At construction it builds the fleet (injecting the clock into each robot) and
registers every robot's actor process and every sensor's publish process. It
then offers a tiny interface:

* `step(dt)` — advance the simulated clock by `dt` seconds,
* `now` — the current simulated time,
* `fleet` — the robots, to be commanded and queried.

### The World (`sim/world.py`)

A top-down grid (`grid_w × grid_h`) holding everything physical:

* **`elevation`** — per-cell terrain height in meters (initialized random-uniform
  within a configured range),
* **`occupancy`** — per-cell boolean of what blocks movement,
* **`blocks` / `anchors`** — placed components,
* **`pod_inflation`**, **`airlock_docked`**, **`pod_deployed`** — habitat state.

The world is pure state with instantaneous mutators — `grade` (average a cell's
elevation with its neighborhood), `excavate` (lower terrain by depth in meters),
`deposit` (raise terrain by height in meters), `set_block`, `set_anchor`. It
models *what* the site is, never *when* — the passage of time belongs to the
robots and the clock. Each grid cell represents 1m² of lunar surface.

### The Robots (`sim/robots.py`)

Robots are bodies on the grid with primitive actuators and no intelligence. Each
runs its own internal process that executes **one command at a time**, spending
simulated time inside the action; commands are non-blocking (they queue, the body
carries them out). Callers read status — `is_idle`, `pos`, `carrying`, `battery`
— to know when to issue the next one. The only movement primitive is a single
cardinal `step`; a robot cannot teleport.

| Kind          | Role                                              | Primitive actions |
| ------------- | ------------------------------------------------- | ----------------- |
| **Loader**    | Mobile earth-mover; carries regolith.             | `step`, `excavate`, `grade`, `unload_ground`, `unload_into` |
| **Producer**  | Stationary plant; sinters regolith into blocks.   | `produce` (+ `ready_blocks` / `take_block`) |
| **Assembler** | Mobile arm; fetches and installs components.      | `step`, `pickup`, `place`, `inflate` |

### Sensors (`sim/sensors/`)

Perception is mediated by robot-mounted sensors, with each robot having its own
sensor configuration. Sensors publish at their own rates, defined per-robot in
the fleet configuration. The built-in `GtSensor` ("ground truth") snapshots the
whole world into an immutable `GtObservation` — elevation, occupancy, placed
anchors/blocks, airlock and pod state. Observations are *latched*: a consumer
always reads the latest published snapshot, subject to the sensor's publish-rate
latency. Different robots can have different sensor update rates based on their
operational needs (e.g., mobile robots may need higher update rates than
stationary producers).

### Building Components

* **Core Pod** — inflatable habitat shipped from Earth (`pod_inflation` 0→1).
* **Anchors** — moon-made spikes that pin the deflated Pod.
* **Blocks** — sintered regolith tiles that form the radiation-shielding shell.
* **Airlock** — rigid docking module shipped from Earth.

### Engine & View

* **SimPy** — discrete-event clock: it fast-forwards through long actions
  (sintering, grading, placing) and runs every robot and sensor concurrently.
* **Pygame** — a top-down "radar" view: terrain heatmap, the foundation disk,
  the inflating Pod, anchors/blocks/airlock, color-coded robots, and a side
  panel with live goal status, fleet state, and an elevation colorbar.

### Configuration (`sim/config.py`)

Everything is data-driven from YAML files, parsed into per-domain **frozen**
Pydantic configs. Configs are separated by concern:

- **`configs/sim.yaml`** — World and simulation settings
  - Grid dimensions (40×40 default)
  - Terrain elevation range (-0.15m to +0.15m)
  - Simulation speed and rendering parameters

- **`configs/fleet.yaml`** — Robot specifications and deployment
  - Individual robot parameters (speed, action times, capacities)
  - Per-robot sensor configurations (type, update rate)
  - Work site locations (depots, pits, production sites)
  - All depths/heights in meters (e.g., `excavate_depth_m: 0.10`)

- **`configs/blueprint.yaml`** — Construction specifications
  - Habitat geometry (pod center, dome/berm radii)
  - Foundation requirements (depth ≥ 0.08m, flatness ≤ 0.05m)
  - Number and placement of anchors

- **`configs/comms.yaml`** — Communication between sim and autonomy
  - ZMQ socket addresses for telemetry and commands
  - Time pacing factor (wall-seconds per sim-second)

- **`configs/autonomy/`** — Autonomy-specific parameters (e.g., `baseline.yaml`)

---

## 2. The Mission: Blueprint & Goals

The mission is specified independently of the simulator, as geometry plus
acceptance criteria.

### Blueprint (`mission/blueprint.py`)

The blueprint derives the base footprint on the grid from a handful of
parameters: `pod_center`, `dome_radius`, `berm_radius`, `num_anchors`, and the
site-prep tolerances. From these it computes the exact target cells:

* **`foundation_cells`** — the disk of radius `berm_radius` around the Pod that
  must be leveled; also exposes mean elevation and flatness (mean absolute
  deviation) helpers.
* **`anchor_cells`** — `num_anchors` spikes evenly spaced around the deflated
  Pod's perimeter.
* **`dome_floor_cells`** — the annulus between `dome_radius` and `berm_radius`,
  tiled with blocks and sorted **innermost-first** so an assembler never traps
  itself behind already-placed blocks.
* **`airlock_cell`** — the dock point just outside the berm.

### Goals (`mission/goals.py`)

A mission is a set of `Goal`s. Each declares an acceptance predicate
(`is_done(observation, blueprint)`) and the goals that must be satisfied first
(`preconditions`), forming a dependency DAG. Progress is judged purely from a
sensor observation, never from privileged world access.

| Goal             | Acceptance criterion                                              | Depends on              |
| ---------------- | ---------------------------------------------------------------- | ----------------------- |
| `site_prep`      | Foundation depth ≥ `min_foundation_depth_m` **and** flatness ≤ `elevation_tolerance_m` | — |
| `anchors`        | Every `anchor_cell` has an anchor placed                          | `site_prep`             |
| `blocks`         | Every `dome_floor_cell` has a block placed                        | `anchors`               |
| `airlock_docked` | Airlock reported docked                                           | `site_prep`             |
| `pod_inflated`   | `pod_inflation` ≥ 0.999                                           | `airlock_docked`, `blocks` |

The DAG leaves room for parallelism — e.g. airlock docking only needs the
foundation, not the full shell — so different controllers can sequence the work
however the preconditions allow.

---

## 3. Running

The sim and the autonomy are **separate processes** that talk over zmq. Start the
sim first (it runs free, robots idle, until a client connects), then the autonomy:

```bash
# Terminal 1 — the sim service (real-time, Pygame view; --headless for no window)
uv run python -m moon_base_sim --sim configs/sim.yaml --fleet configs/fleet.yaml \
    --blueprint configs/blueprint.yaml --comms configs/comms.yaml

# Terminal 2 — an autonomy that connects and drives the fleet (no sim config needed!)
uv run python -m moon_base_sim.autonomy --fleet configs/fleet.yaml \
    --blueprint configs/blueprint.yaml --comms configs/comms.yaml
```

The sim paces sim-time to wall-time by `comms.factor` (wall-seconds per sim-second;
`--factor` overrides). You can stop and restart the autonomy at any time — the sim
keeps running and re-attaches. Socket addresses come from `comms.{telemetry_addr,
command_addr}` (`--telemetry` / `--commands` override).

---

## 4. Build your own autonomy

An autonomy is any process that subscribes to the sim's telemetry and publishes
commands. The baseline (`autonomy/baseline/policy.py`) is the reference
implementation; the wire contract is below.

### Wiring (zmq, pickled payloads)

| Channel    | Sim socket        | Autonomy socket    | Carries |
| ---------- | ----------------- | ------------------ | ------- |
| telemetry  | **PUB** (bind `telemetry_addr`) | **SUB** (connect) | `(topic, message)` |
| commands   | **PULL** (bind `command_addr`)  | **PUSH** (connect) | `Command` |

Messages are pickled Python objects (`comms/messages.py`). The `comms.transport`
helpers (`SimEndpoint`, `AutonomyEndpoint`) wrap the sockets; the reusable client
harness in `autonomy/client.py` builds a world `Model` and runs any policy.

### Telemetry topics & messages

| Topic    | Message        | When | Key fields |
| -------- | -------------- | ---- | ---------- |
| `obs`    | `GtObservation` | each sensor period (`sensors.gt.publish_hz`) | `w,h, elevation, occupancy, anchors, blocks, airlock_docked, pod_inflation` |
| `status` | `RobotStatus`   | per robot, on every state change + heartbeat | `rid, kind, pos, is_idle, carrying, regolith, regolith_inventory, done_seq, t` |
| `blocks` | `BlockReady`    | when a producer finishes a block | `producer_rid, coord, t` |

### Commands (`Command(rid, seq, verb, args)`)

| verb            | args             | effect |
| --------------- | ---------------- | ------ |
| `step`          | `("up"\|"down"\|"left"\|"right",)` | move one cell |
| `excavate`/`grade`/`unload_ground` | `(cell,)` | loader acts at its current cell |
| `feed`          | `(producer_rid,)` | loader unloads cargo into a producer |
| `pickup`        | `(item,)`        | assembler grabs `"anchor"\|"block"\|"airlock"` |
| `place`         | `(cell,)`        | assembler installs the carried item |
| `produce`       | `()`             | producer converts feedstock into a block |
| `inflate`       | `()`             | assembler inflates the pod |

### Contract an autonomy must honor

- Build a world/fleet model from telemetry; address robots by `rid`. Robots are
  dumb — **pathfinding is yours** (issue one `step` at a time toward a goal).
- **One outstanding command per robot.** Each `Command` carries an incrementing
  `seq`; a robot echoes the last finished `done_seq` in `status`. A robot is ready
  for its next command when `done_seq == the last seq you sent it`.
- Claim produced blocks locally from the `blocks` stream (you are the only consumer).
- The sim runs whether or not you are connected; expect to join late and miss nothing
  durable (telemetry is periodic state).

### Minimal client

```python
from moon_base_sim.comms import AutonomyEndpoint, STATUS, Command

ep = AutonomyEndpoint("tcp://127.0.0.1:5555", "tcp://127.0.0.1:5556")
seq = {}
while True:
    for topic, msg in ep.poll(50):
        if topic == STATUS and msg.kind == "loader" and msg.done_seq == seq.get(msg.rid, 0):
            seq[msg.rid] = seq.get(msg.rid, 0) + 1
            ep.send(Command(msg.rid, seq[msg.rid], "step", ("right",)))   # crawl east
```

Register a full policy class (with `decide(model) -> [Command]` and
`mission_done(model)`) in `autonomy/__init__.py`'s `_REGISTRY` and select it with
`--autonomy <name>`.
