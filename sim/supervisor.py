"""Phase quality-assurance checks.

Each ``check_phaseN`` returns ``(ok, reason)`` describing whether the world
has actually achieved that phase's goals. ``check(phase, world)`` is a small
dispatcher used by the orchestrator.
"""
from __future__ import annotations

from . import blueprint
from .config import CONFIG
from .world import World


def check_phase1(world: World) -> tuple[bool, str]:
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


def check_phase2(world: World) -> tuple[bool, str]:
    expected_anchors = set(blueprint.anchor_cells())
    expected_blocks = set(blueprint.dome_floor_cells())
    a_missing = expected_anchors - world.anchors
    b_missing = expected_blocks - world.blocks
    summary = (
        f"anchors {len(world.anchors)}/{len(expected_anchors)} "
        f"blocks {len(world.blocks)}/{len(expected_blocks)}"
    )
    if a_missing or b_missing:
        return False, summary
    return True, summary


def check_phase3(world: World) -> tuple[bool, str]:
    pct = int(world.pod_inflation * 100)
    summary = f"docked={world.airlock_docked} inflated={pct}%"
    if not world.airlock_docked:
        return False, summary
    if world.pod_inflation < 0.999:
        return False, summary
    return True, summary


def check(phase: int, world: World) -> tuple[bool, str]:
    if phase == 1:
        return check_phase1(world)
    if phase == 2:
        return check_phase2(world)
    if phase == 3:
        return check_phase3(world)
    return True, ""
