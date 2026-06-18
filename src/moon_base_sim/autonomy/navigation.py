"""Pathfinding for the autonomy — pure A* over a perceived observation.

Robots only ever take a single `step`; the policy calls :func:`next_step` each
tick to pick the next cardinal move toward a goal. No simulated time, no SimPy.
"""
from __future__ import annotations

import heapq
from typing import Callable, Optional

from ..sim.robots import Direction
from ..sim.sensors import GtObservation

Coord = tuple[int, int]

NEIGHBORS_4 = [(1, 0), (-1, 0), (0, 1), (0, -1)]

_DELTA_TO_DIR = {d.value: d for d in Direction}


def manhattan(a: Coord, b: Coord) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _passable(obs: GtObservation, self_pos: Coord) -> Callable[[int, int], bool]:
    def ok(x: int, y: int) -> bool:
        if not obs.in_bounds(x, y):
            return False
        if (x, y) == self_pos:
            return True
        return not obs.occupancy[y][x]

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


def next_step(obs: GtObservation, pos: Coord, goal: Coord) -> Optional[Direction]:
    """Next cardinal step from `pos` toward `goal`; None if arrived/blocked/no path."""
    if pos == goal:
        return None
    path = astar(pos, goal, _passable(obs, pos))
    if not path or len(path) < 2:
        return None
    nx, ny = path[1]
    if obs.is_blocked(nx, ny) and (nx, ny) != goal:
        return None
    return _DELTA_TO_DIR[(nx - pos[0], ny - pos[1])]
