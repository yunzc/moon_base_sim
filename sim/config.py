from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimConfig:
    grid_w: int = 60
    grid_h: int = 40
    cell_size: int = 16

    pod_center: tuple[int, int] = (30, 20)
    dome_radius: int = 6
    berm_radius: int = 10

    num_loaders: int = 3
    num_producers: int = 2
    num_assemblers: int = 2

    loader_speed: float = 1.0
    assembler_speed: float = 0.8

    grade_time: float = 2.0
    produce_time: float = 6.0
    anchor_drive_time: float = 4.0
    block_place_time: float = 3.0
    dock_time: float = 8.0

    regolith_per_block: int = 3
    num_anchors: int = 8

    elevation_tolerance_cm: float = 5.0
    dock_tolerance_mm: float = 1.0

    sim_speed: float = 20.0
    target_fps: int = 30


CONFIG = SimConfig()

LOADER_DEPOT = (2, 2)
PRODUCER_SITES: list[tuple[int, int]] = [(5, 35), (55, 35)]
ASSEMBLER_DEPOT = (55, 5)
