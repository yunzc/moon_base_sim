from __future__ import annotations

from .config import CONFIG


def dome_floor_cells() -> list[tuple[int, int]]:
    """Tiled floor of the dome: every foundation cell outside the inflated core.

    The core (Pod) inflates to ``dome_radius``; the foundation extends to
    ``berm_radius``. Blocks tile the annulus between them, sorted from
    innermost to outermost so assemblers can place without trapping themselves
    behind already-set blocks.
    """
    cx, cy = CONFIG.pod_center
    r_inner = CONFIG.dome_radius
    r_outer = CONFIG.berm_radius
    cells: list[tuple[int, int]] = []
    for y in range(cy - r_outer, cy + r_outer + 1):
        for x in range(cx - r_outer, cx + r_outer + 1):
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if r_inner * r_inner < d2 <= r_outer * r_outer:
                cells.append((x, y))
    cells.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
    return cells


def anchor_cells() -> list[tuple[int, int]]:
    """Anchor spike locations around the deflated Pod perimeter."""
    cx, cy = CONFIG.pod_center
    n = CONFIG.num_anchors
    import math

    r = CONFIG.dome_radius - 2
    out: list[tuple[int, int]] = []
    for i in range(n):
        theta = (2 * math.pi * i) / n
        x = int(round(cx + r * math.cos(theta)))
        y = int(round(cy + r * math.sin(theta)))
        out.append((x, y))
    return out


def airlock_cell() -> tuple[int, int]:
    cx, cy = CONFIG.pod_center
    return (cx + CONFIG.berm_radius + 1, cy)
