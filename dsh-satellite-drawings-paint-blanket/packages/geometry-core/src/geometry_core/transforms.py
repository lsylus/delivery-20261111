"""Policy-neutral rigid transforms plus CAD assembly shape placement."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TypeAlias

import cadquery as cq
import numpy as np
from OCP.TopLoc import TopLoc_Location
from OCP.gp import gp_Trsf


Vector3: TypeAlias = tuple[float, float, float]
Matrix3: TypeAlias = tuple[Vector3, Vector3, Vector3]


@dataclass(frozen=True, slots=True)
class RigidTransform:
    """One rigid transform with row-major rotation and millimeter translation."""

    rotation: Matrix3
    translation_mm: Vector3


def rigid_transform_from_values(
    rotation: Sequence[Sequence[float]],
    translation_mm: Sequence[float],
) -> RigidTransform:
    """Normalize list/array values into the immutable transform contract."""
    rows: Matrix3 = tuple(
        tuple(float(value) for value in row)
        for row in rotation
    )  # type: ignore[assignment]
    translation: Vector3 = tuple(
        float(value) for value in translation_mm
    )  # type: ignore[assignment]
    if len(rows) != 3 or any(len(row) != 3 for row in rows):
        raise ValueError("rigid rotation must be a 3x3 matrix")
    if len(translation) != 3:
        raise ValueError("rigid translation must have three values")
    matrix = np.asarray(rows, dtype=float)
    if not np.isfinite(matrix).all() or not np.isfinite(translation).all():
        raise ValueError("non-finite rigid transform")
    if not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-9, rtol=0) or abs(np.linalg.det(matrix)-1)>1e-9:
        raise ValueError("transform must be right-handed rigid; mirror/scale rejected")
    return RigidTransform(rotation=rows, translation_mm=translation)


def relative_rigid_transform(
    *,
    source_rotation: Sequence[Sequence[float]],
    source_anchor_mm: Sequence[float],
    target_rotation: Sequence[Sequence[float]],
    target_anchor_mm: Sequence[float],
) -> RigidTransform:
    """Map a source frame to a target frame using caller-selected anchors.

    Rotations are row-major. Anchors may be frame origins or shape centers;
    this function does not choose anchors, normalize axes, or round values.
    """
    rotation = np.asarray(target_rotation) @ np.asarray(source_rotation).T
    translation = (
        np.asarray(target_anchor_mm, dtype=float)
        - rotation @ np.asarray(source_anchor_mm, dtype=float)
    )
    return rigid_transform_from_values(rotation, translation)


def rigid_transform_from_axes(
    *,
    origin_mm: Sequence[float],
    x_axis: Sequence[float],
    y_axis: Sequence[float],
    z_axis: Sequence[float],
) -> RigidTransform:
    """Convert public axis columns into the row-major transform contract."""
    axes = (x_axis, y_axis, z_axis)
    return rigid_transform_from_values(
        [
            [axes[column][row] for column in range(3)]
            for row in range(3)
        ],
        origin_mm,
    )


def rigid_transform_from_location(location: TopLoc_Location) -> RigidTransform:
    """Read an OCCT location without service-specific rounding."""
    value = location.Transformation()
    return rigid_transform_from_values(
        [
            [value.Value(row, column) for column in range(1, 4)]
            for row in range(1, 4)
        ],
        [value.Value(row, 4) for row in range(1, 4)],
    )


def location_from_rigid_transform(transform: RigidTransform) -> TopLoc_Location:
    """Build an OCCT location from the row-major transform contract."""
    rigid_transform_from_values(transform.rotation, transform.translation_mm)
    value = gp_Trsf()
    value.SetValues(*(
        component
        for row, translation in zip(
            transform.rotation, transform.translation_mm, strict=True
        )
        for component in (*row, translation)
    ))
    return TopLoc_Location(value)


def move_topods_shape(shape, transform: RigidTransform, *, inverse: bool = False):
    """Return a located copy of a native shape in the requested direction."""
    location = location_from_rigid_transform(transform)
    return shape.Moved(location.Inverted() if inverse else location)


def transform_document(transform: RigidTransform) -> dict:
    return {"kind": "rigid", "layout": "row_major", "action": "column_vector", "matrix": [[*row, t] for row, t in zip(transform.rotation, transform.translation_mm)] + [[0., 0., 0., 1.]]}

def compose(parent: RigidTransform, local: RigidTransform) -> RigidTransform:
    rigid_transform_from_values(parent.rotation, parent.translation_mm)
    rigid_transform_from_values(local.rotation, local.translation_mm)
    r = np.asarray(parent.rotation) @ np.asarray(local.rotation)
    t = np.asarray(parent.rotation) @ np.asarray(local.translation_mm) + parent.translation_mm
    return rigid_transform_from_values(r, t)
