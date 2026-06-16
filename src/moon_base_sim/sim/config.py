from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimConfig:
    cell_size: int = 16

    num_anchors: int = 8

    elevation_tolerance_cm: float = 5.0
    min_foundation_depth_cm: float = 8.0
    dock_tolerance_mm: float = 1.0

    sim_speed: float = 20.0
    target_fps: int = 30


CONFIG = SimConfig()

LOADER_DEPOT = (2, 2)
PRODUCER_SITES: list[tuple[int, int]] = [(5, 35), (35, 35)]
ASSEMBLER_DEPOT = (37, 5)
REGOLITH_PITS: list[tuple[int, int]] = [(8, 35), (32, 35)]
SPOIL_SITE = (5, 5)
