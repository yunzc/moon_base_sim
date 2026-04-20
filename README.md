# moon_base_sim


## 1. Vision: The "Blank Slate" Approach
This simulation explores automated construction on the Moon, assuming a environment free from legacy Earth-based construction constraints. It focuses on full autonomy, deterministic logic, and local resource utilization.

---

## 2. The Architectural Framework

### Machine Actors
* **Loaders:** Mobile agents that excavate, grade, and transport raw regolith.
* **Producers:** Stationary units that process regolith into standardized building parts (Sintering/Molding).
* **Assemblers:** High-precision mobile arms that place components according to the architectural blueprint.

### Building Components
* **Core Pod:** Inflatable habitat module (shipped from Earth).
* **Anchors:** Moon-made spikes to secure the Pod.
* **Blocks:** Sintered regolith blocks for radiation shielding.
* **Airlock:** Rigid docking module (shipped from Earth).

---

## 3. The Construction Phases

### Phase 1: Site Preparation
* **Objective:** Create a level, compacted foundation and a protective berm.
* **Logic:** Loaders modify terrain voxels until variance is within tolerance.
* **Success Metric:** Average elevation deviation < 5cm.

### Phase 2: Protective Shell
* **Objective:** Build a self-supporting compression vault (dome) over the Core Pod.
* **Logic:** 1. Assemblers drive Anchors through the deflated Pod.
    2. Producers output Blocks.
    3. Assemblers stack Blocks using a 3D blueprint matrix.
* **Constraint:** Geometry must be stable under 1/6g gravity without mortar.

### Phase 3: Deployment & Docking
* **Objective:** Mate the Airlock to the Pod and inflate the habitat.
* **Logic:** High-precision alignment check (millimeter tolerance).
* **Success Metric:** Successful seal allows for Pod expansion.

---

## 4. Technical Simulation Stack

### Brain: SimPy (Discrete Event Simulation)
* **Role:** Manages the orchestration, timing, and resource bottlenecks.
* **Advantages:** Efficiently "fast-forwards" through long processing times; handles concurrent robot tasks and dependency gates.

### Eyes: Pygame (2D Visualization)
* **Role:** Provides a top-down "Radar" view of the construction site.
* **Features:**
    * **Grid System:** 2D coordinate map of the moon base site.
    * **Robot Visualization:** Color-coded agents moving in real-time.
    * **State Overlay:** Live stats on block counts, battery levels, and phase progress.

### Navigation: A* (A-Star) Pathfinding
* **Role:** Allows robots to find the shortest path while avoiding the growing shell and other robots.
* **Logic:** Dynamic occupancy grid updates every time a block is placed.

---

## 5. Key Simulation Goals
1.  **Optimization:** Find the "Sweet Spot" for the number of robots (avoiding traffic jams).
2.  **Robustness:** Simulate machine failures and calculate the impact on the mission timeline.
3.  **Feasibility:** Validate if the proposed "Phase 1-3" sequence is logically sound under strict mechanical constraints.
