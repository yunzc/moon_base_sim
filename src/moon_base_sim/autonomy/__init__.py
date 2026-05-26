"""Pluggable autonomy modules. Pick one with ``load_autonomy(name)``."""
from __future__ import annotations

import importlib

from .base import Autonomy, AutonomyState

__all__ = ["Autonomy", "AutonomyState", "load_autonomy"]

_REGISTRY: dict[str, str] = {
    "baseline": "moon_base_sim.autonomy.baseline:Baseline",
}


def load_autonomy(name: str) -> Autonomy:
    try:
        target = _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY))
        raise SystemExit(f"unknown autonomy {name!r}; known: {known}")
    module_path, cls_name = target.split(":")
    module = importlib.import_module(module_path)
    return getattr(module, cls_name)()
