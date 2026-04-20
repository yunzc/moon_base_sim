from __future__ import annotations

from .config import CONFIG


def dome_ring_cells() -> list[tuple[int, int]]:
    """2D footprint of the compression vault: an annulus one cell thick.

    In a full 3D sim each ring would be stacked into a hemisphere; the 2D view
    collapses that into a single ring of blocks surrounding the Pod.
    """
    cx, cy = CONFIG.pod_center
    r = CONFIG.dome_radius
    cells: list[tuple[int, int]] = []
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            dx, dy = x - cx, y - cy
            d2 = dx * dx + dy * dy
            if (r - 1) * (r - 1) < d2 <= r * r:
                cells.append((x, y))
    cells.sort(key=lambda c: (c[1], c[0]))
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
    return (cx + CONFIG.dome_radius + 1, cy)
