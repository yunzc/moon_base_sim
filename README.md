# moon_base_sim

A discrete-event simulation of automated lunar base construction: a fleet of
robots excavates terrain, sinters regolith into blocks, and assembles a shielded
habitat — all on a top-down grid, advanced by a SimPy clock and watchable through
a Pygame view.

This document covers the **simulator** (the world the robots live in) and the
**mission spec** (the blueprint geometry and the goals that define "done"). The
control layer that drives the robots is documented separately.

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

* **`elevation`** — per-cell terrain height in cm (initialized random-uniform
  within a configured range),
* **`occupancy`** — per-cell boolean of what blocks movement,
* **`blocks` / `anchors`** — placed components,
* **`pod_inflation`**, **`airlock_docked`**, **`pod_deployed`** — habitat state.

The world is pure state with instantaneous mutators — `grade` (average a cell
with its neighborhood), `excavate` (lower), `deposit` (raise), `set_block`,
`set_anchor`. It models *what* the site is, never *when* — the passage of time
belongs to the robots and the clock.

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

Perception is mediated by robot-mounted sensors, each publishing at its own rate.
The built-in `GtSensor` ("ground truth") snapshots the whole world into an
immutable `GtObservation` — elevation, occupancy, placed anchors/blocks, airlock
and pod state. Observations are *latched*: a consumer always reads the latest
published snapshot, subject to the sensor's publish-rate latency.

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

Everything is data-driven from a single YAML file (see `configs/default.yaml`),
parsed into per-domain **frozen** Pydantic configs: `sim`, `world`, `blueprint`,
`robots` (fleet composition), `layout` (fixed site positions), and `sensors`.

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
| `site_prep`      | Foundation depth ≥ `min_foundation_depth_cm` **and** flatness ≤ `elevation_tolerance_cm` | — |
| `anchors`        | Every `anchor_cell` has an anchor placed                          | `site_prep`             |
| `blocks`         | Every `dome_floor_cell` has a block placed                        | `anchors`               |
| `airlock_docked` | Airlock reported docked                                           | `site_prep`             |
| `pod_inflated`   | `pod_inflation` ≥ 0.999                                           | `airlock_docked`, `blocks` |

The DAG leaves room for parallelism — e.g. airlock docking only needs the
foundation, not the full shell — so different controllers can sequence the work
however the preconditions allow.

---

## 3. Running

```bash
# Top-down Pygame view
uv run python -m moon_base_sim --config configs/default.yaml

# Headless (no window), with a time budget and fixed terrain seed
uv run python -m moon_base_sim --config configs/default.yaml --headless \
    --seed 0 --max-time 30000
```
