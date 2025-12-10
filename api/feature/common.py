# api/feature/common.py
from __future__ import annotations
from typing import Tuple, Type

class AxisError(RuntimeError):
    """Axis string could not be mapped to a unit vector."""


def axis_to_vector(axis: str, *, error_cls: Type[Exception] = AxisError) -> Tuple[float, float, float]:
    """Map "+Z", "-X", etc. to a unit vector; raise error_cls on unknown."""
    a = axis.strip().upper()
    mapping = {
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    if a not in mapping:
        raise error_cls(f"Unsupported axis: {axis}")
    return mapping[a]
