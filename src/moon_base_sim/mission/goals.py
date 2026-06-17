"""Mission goals and acceptance criteria.

The mission spec is a set of goals. Each goal declares an acceptance predicate
(``is_done``) and the names of other goals that must be satisfied first
(``preconditions``). The autonomy decides how to satisfy them; the baseline
walks the DAG linearly but a smarter autonomy could parallelize anywhere
preconditions allow.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from ..sim.sensors import GtObservation
    from .blueprint import Blueprint


def check_site_prep(obs: "GtObservation", blueprint: "Blueprint") -> tuple[bool, str]:
    f_cells = list(blueprint.foundation_cells(obs))
    if not f_cells:
        return False, "no foundation cells"
    f_set = set(f_cells)
    f_vals = [obs.elevation[y][x] for x, y in f_cells]
    f_mean = sum(f_vals) / len(f_vals)

    s_vals = [
        obs.elevation[y][x]
        for y in range(obs.h)
        for x in range(obs.w)
        if (x, y) not in f_set
    ]
    s_mean = sum(s_vals) / len(s_vals) if s_vals else 0.0

    depth = s_mean - f_mean
    flatness = sum(abs(v - f_mean) for v in f_vals) / len(f_vals)

    summary = f"depth={depth:.1f}cm flat={flatness:.1f}cm"
    cfg = blueprint.config
    issues: list[str] = []
    if depth < cfg.min_foundation_depth_cm:
        issues.append(f"need ≥{cfg.min_foundation_depth_cm:.0f}cm deep")
    if flatness > cfg.elevation_tolerance_cm:
        issues.append(f"need ≤{cfg.elevation_tolerance_cm:.0f}cm rough")
    if issues:
        return False, summary + " | " + ", ".join(issues)
    return True, summary


def check_anchors(obs: "GtObservation", blueprint: "Blueprint") -> tuple[bool, str]:
    expected = set(blueprint.anchor_cells())
    missing = expected - obs.anchors
    summary = f"anchors {len(obs.anchors)}/{len(expected)}"
    return (not missing, summary)


def check_blocks(obs: "GtObservation", blueprint: "Blueprint") -> tuple[bool, str]:
    expected = set(blueprint.dome_floor_cells())
    missing = expected - obs.blocks
    summary = f"blocks {len(obs.blocks)}/{len(expected)}"
    return (not missing, summary)


def check_airlock_docked(obs: "GtObservation", blueprint: "Blueprint") -> tuple[bool, str]:
    return obs.airlock_docked, f"docked={obs.airlock_docked}"


def check_pod_inflated(obs: "GtObservation", blueprint: "Blueprint") -> tuple[bool, str]:
    pct = int(obs.pod_inflation * 100)
    return obs.pod_inflation >= 0.999, f"inflated={pct}%"


@dataclass(frozen=True)
class Goal:
    name: str
    label: str
    preconditions: tuple[str, ...]
    is_done: Callable[["GtObservation", "Blueprint"], tuple[bool, str]]


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
