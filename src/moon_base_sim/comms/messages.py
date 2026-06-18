"""Wire messages exchanged between the sim and an autonomy. Pure data, no refs."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Telemetry topics (sim -> autonomy). The obs payload is a sensors.GtObservation.
OBS = "obs"
STATUS = "status"
BLOCKS = "blocks"


@dataclass(frozen=True)
class RobotStatus:
    """Per-robot telemetry, published on STATUS at each state change."""

    rid: str
    kind: str
    pos: tuple[int, int]
    is_idle: bool
    carrying: Optional[str]
    regolith: int            # loader cargo (0 for others)
    regolith_inventory: int  # producer feedstock (0 for others)
    done_seq: int            # seq of the last command this robot finished
    t: float                 # sim time of publish


@dataclass(frozen=True)
class BlockReady:
    """A producer finished a block, available for pickup at ``coord``."""

    producer_rid: str
    coord: tuple[int, int]
    t: float


@dataclass(frozen=True)
class Command:
    """An autonomy -> robot command. ``verb`` + plain ``args`` (no object refs)."""

    rid: str
    seq: int
    verb: str            # step|excavate|grade|unload_ground|feed|pickup|place|produce|inflate
    args: tuple = field(default_factory=tuple)
