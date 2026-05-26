"""Mission specification: what to build (blueprint) and how success is judged (supervisor).

Mission is invariant across autonomy implementations — any autonomy must satisfy
the same blueprint and pass the same supervisor checks.
"""
from . import blueprint, goals

__all__ = ["blueprint", "goals"]
