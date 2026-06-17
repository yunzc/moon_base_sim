"""Navigation for autonomy implementations.

Pathfinding (A*) and path-following live here, not in the simulated robot.
A robot's only movement capability is a single cardinal `step`; the autonomy
module decides *where* to go and walks the robot there one cell at a time.
"""
from __future__ import annotations

import heapq
from typing import Callable

import simpy

from ..sim.robots import Direction, Robot
from ..sim.world import World

Coord = tuple[int, int]

NEIGHBORS_4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]

_DELTA_TO_DIR = {d.value: d for d in Direction}


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _passable(world: World, self_pos: Coord) -> Callable[[int, int], bool]:
    def ok(x: int, y: int) -> bool:
        if not world.in_bounds(x, y):
            return False
        if (x, y) == self_pos:
            return True
        return not world.occupancy[y][x]

    return ok


def astar(
    start: Coord,
    goal: Coord,
    passable: Callable[[int, int], bool],
) -> list[Coord]:
    """Standard 4-connected A*. Returns [] when no path exists.

    `passable(x, y)` must return True for cells the agent may enter. The goal
    cell is treated as reachable even if occupied, so agents can arrive
    adjacent to their target without needing the target itself free.
    """
    if start == goal:
        return [start]

    open_heap: list[tuple[int, int, Coord]] = []
    heapq.heappush(open_heap, (0, 0, start))
    came_from: dict[Coord, Coord] = {}
    g_score: dict[Coord, int] = {start: 0}
    counter = 0

    while open_heap:
        _, _, current = heapq.heappop(open_heap)
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        for dx, dy in NEIGHBORS_4:
            nx, ny = current[0] + dx, current[1] + dy
            neighbor = (nx, ny)
            if neighbor != goal and not passable(nx, ny):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(neighbor, 10**9):
                came_from[neighbor] = current
                g_score[neighbor] = tentative
                f = tentative + manhattan(neighbor, goal)
                counter += 1
                heapq.heappush(open_heap, (f, counter, neighbor))

    return []


def navigate(
    env: simpy.Environment, world: World, robot: Robot, goal: Coord
):
    """Walk `robot` to `goal` one cardinal step at a time, re-planning each cell.

    Drives the robot purely through its `step` primitive: A* picks the next
    cell, this converts the delta to a `Direction`, and the robot moves. Waits
    in place when blocked by a dynamic obstacle, mirroring the previous
    in-robot `move_to` behavior.
    """
    while robot.pos != goal:
        path = astar(robot.pos, goal, _passable(world, robot.pos))
        if not path or len(path) < 2:
            yield env.timeout(0.5)
            continue
        nx, ny = path[1]
        if world.is_blocked(nx, ny) and (nx, ny) != goal:
            yield env.timeout(0.2)
            continue
        direction = _DELTA_TO_DIR[(nx - robot.x, ny - robot.y)]
        yield from robot.step(env, world, direction)
