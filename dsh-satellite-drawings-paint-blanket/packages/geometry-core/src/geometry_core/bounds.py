"""Policy-neutral axis-aligned bounds primitives over OCCT shapes."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


Vector3: TypeAlias = tuple[float, float, float]
Bounds6: TypeAlias = tuple[float, float, float, float, float, float]


class BoundsStrategy(str, Enum):
    """OCCT algorithms whose accuracy and tolerance behavior are explicit."""

    OPTIMAL_WITHOUT_SHAPE_TOLERANCE = "optimal_without_shape_tolerance"
    OPTIMAL_WITH_SHAPE_TOLERANCE = "optimal_with_shape_tolerance"
    CONSERVATIVE_WITHOUT_TRIANGULATION = "conservative_without_triangulation"


@dataclass(frozen=True, slots=True)
class ShapeBounds:
    """Raw six-value OCCT bounds without service rounding or error mapping."""

    values: Bounds6

    @classmethod
    def from_box(cls, box: Bnd_Box) -> "ShapeBounds":
        """Read one native box; OCCT retains its native void-box exception."""
        return cls(tuple(float(value) for value in box.Get()))  # type: ignore[arg-type]

    @property
    def minimum(self) -> Vector3:
        return self.values[:3]  # type: ignore[return-value]

    @property
    def maximum(self) -> Vector3:
        return self.values[3:]  # type: ignore[return-value]

    @property
    def dimensions(self) -> Vector3:
        return tuple(
            self.values[index + 3] - self.values[index]
            for index in range(3)
        )  # type: ignore[return-value]


def shape_bounds_box(shape, *, strategy: BoundsStrategy) -> Bnd_Box:
    """Build a native box with an explicit accuracy/tolerance strategy."""
    box = Bnd_Box()
    if strategy is BoundsStrategy.OPTIMAL_WITHOUT_SHAPE_TOLERANCE:
        BRepBndLib.AddOptimal_s(shape, box, True, False)
    elif strategy is BoundsStrategy.OPTIMAL_WITH_SHAPE_TOLERANCE:
        BRepBndLib.AddOptimal_s(shape, box)
    elif strategy is BoundsStrategy.CONSERVATIVE_WITHOUT_TRIANGULATION:
        BRepBndLib.Add_s(shape, box, False)
    else:  # pragma: no cover - Enum callers cannot reach this branch normally.
        raise ValueError(f"unsupported bounds strategy: {strategy!r}")
    return box


def measure_shape_bounds(shape, *, strategy: BoundsStrategy) -> ShapeBounds:
    """Measure raw shape bounds without applying either service's policy."""
    return ShapeBounds.from_box(shape_bounds_box(shape, strategy=strategy))


def bounds_gap(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the Euclidean separation of two AABBs; touching/overlap is zero."""
    return math.sqrt(sum(
        max(left[index] - right[index + 3], right[index] - left[index + 3], 0.) ** 2
        for index in range(3)
    ))
