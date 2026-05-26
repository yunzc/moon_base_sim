from dataclasses import dataclass, field


@dataclass(frozen=True)
class SimConfig:
    grid_w: int = 40
    grid_h: int = 40
    cell_size: int = 16

    pod_center: tuple[int, int] = (20, 20)
    dome_radius: int = 6
    berm_radius: int = 10

    num_loaders: int = 3
    num_producers: int = 2
    num_assemblers: int = 2

    loader_speed: float = 1.0
    producer_speed: float = 0.5
    assembler_speed: float = 0.8

    grade_time: float = 2.0
    excavate_time: float = 1.0
    unload_time: float = 1.0
    produce_time: float = 6.0
    anchor_drive_time: float = 4.0
    block_place_time: float = 3.0
    dock_time: float = 8.0
    inflate_time: float = 6.0

    loader_capacity: int = 4
    regolith_per_block: int = 3
    regolith_per_excavate_cm: float = 10.0
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
