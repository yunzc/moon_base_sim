"""Mission goals and acceptance criteria.

The mission spec is a set of goals. Each goal declares an acceptance predicate
(``is_done``) and the names of other goals that must be satisfied first
(``preconditions``). The autonomy decides how to satisfy them; the baseline
walks the DAG linearly but a smarter autonomy could parallelize anywhere
preconditions allow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..sim.config import CONFIG
from ..sim.world import World
from . import blueprint


def check_site_prep(world: World) -> tuple[bool, str]:
    f_cells = list(world.foundation_cells())
    if not f_cells:
        return False, "no foundation cells"
    f_set = set(f_cells)
    f_vals = [world.elevation[y][x] for x, y in f_cells]
    f_mean = sum(f_vals) / len(f_vals)

    s_vals = [
        world.elevation[y][x]
        for y in range(world.h)
        for x in range(world.w)
        if (x, y) not in f_set
    ]
    s_mean = sum(s_vals) / len(s_vals) if s_vals else 0.0

    depth = s_mean - f_mean
    flatness = sum(abs(v - f_mean) for v in f_vals) / len(f_vals)

    summary = f"depth={depth:.1f}cm flat={flatness:.1f}cm"
    issues: list[str] = []
    if depth < CONFIG.min_foundation_depth_cm:
        issues.append(f"need ≥{CONFIG.min_foundation_depth_cm:.0f}cm deep")
    if flatness > CONFIG.elevation_tolerance_cm:
        issues.append(f"need ≤{CONFIG.elevation_tolerance_cm:.0f}cm rough")
    if issues:
        return False, summary + " | " + ", ".join(issues)
    return True, summary


def check_anchors(world: World) -> tuple[bool, str]:
    expected = set(blueprint.anchor_cells())
    missing = expected - world.anchors
    summary = f"anchors {len(world.anchors)}/{len(expected)}"
    return (not missing, summary)


def check_blocks(world: World) -> tuple[bool, str]:
    expected = set(blueprint.dome_floor_cells())
    missing = expected - world.blocks
    summary = f"blocks {len(world.blocks)}/{len(expected)}"
    return (not missing, summary)


def check_airlock_docked(world: World) -> tuple[bool, str]:
    return world.airlock_docked, f"docked={world.airlock_docked}"


def check_pod_inflated(world: World) -> tuple[bool, str]:
    pct = int(world.pod_inflation * 100)
    return world.pod_inflation >= 0.999, f"inflated={pct}%"


@dataclass(frozen=True)
class Goal:
    name: str
    label: str
    preconditions: tuple[str, ...]
    is_done: Callable[[World], tuple[bool, str]]


SITE_PREP = Goal(
    "site_prep", "Site Prep", (), check_site_prep
)
ANCHORS = Goal(
    "anchors", "Anchors", ("site_prep",), check_anchors
)
BLOCKS = Goal(
    "blocks", "Blocks", ("anchors",), check_blocks
)
AIRLOCK_DOCKED = Goal(
    "airlock_docked", "Airlock docked", ("site_prep",), check_airlock_docked
)
POD_INFLATED = Goal(
    "pod_inflated", "Pod inflated", ("airlock_docked", "blocks"), check_pod_inflated
)

GOALS: list[Goal] = [SITE_PREP, ANCHORS, BLOCKS, AIRLOCK_DOCKED, POD_INFLATED]
