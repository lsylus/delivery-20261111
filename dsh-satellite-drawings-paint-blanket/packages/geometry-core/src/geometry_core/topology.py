"""Policy-neutral unique topology and solid-face coverage facts."""

from __future__ import annotations

from dataclasses import dataclass

import cadquery as cq
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SHELL, TopAbs_SOLID
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape


@dataclass(frozen=True, slots=True)
class ShapeTopology:
    """Unique OCCT subshape counts without acceptance or publication policy."""

    solid_count: int
    shell_count: int
    face_count: int
    solid_face_count: int
    non_solid_face_count: int
    valid: bool

    def __post_init__(self) -> None:
        counts = (
            self.solid_count,
            self.shell_count,
            self.face_count,
            self.solid_face_count,
            self.non_solid_face_count,
        )
        if any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in counts
        ):
            raise ValueError("topology counts must be non-negative integers")
        if not isinstance(self.valid, bool):
            raise TypeError("valid must be a boolean")
        if self.solid_face_count + self.non_solid_face_count != self.face_count:
            raise ValueError("solid and non-solid face counts must cover all faces")

    @property
    def complete_solid_faces(self) -> bool:
        """Whether every one of at least one face belongs to a solid."""
        return self.face_count > 0 and self.non_solid_face_count == 0


def measure_shape_topology(shape) -> ShapeTopology:
    """Measure unique topology facts from a CadQuery or native OCCT shape."""
    native = shape.wrapped if isinstance(shape, cq.Shape) else shape
    if native.IsNull():
        raise ValueError("cannot measure topology of a null shape")
    solids = _mapped_shapes(native, TopAbs_SOLID)
    shells = _mapped_shapes(native, TopAbs_SHELL)
    faces = _mapped_shapes(native, TopAbs_FACE)
    solid_faces = TopTools_IndexedMapOfShape()
    for index in range(1, solids.Extent() + 1):
        TopExp.MapShapes_s(solids.FindKey(index), TopAbs_FACE, solid_faces)
    non_solid_faces = sum(
        not solid_faces.Contains(faces.FindKey(index))
        for index in range(1, faces.Extent() + 1)
    )
    return ShapeTopology(
        solid_count=solids.Extent(),
        shell_count=shells.Extent(),
        face_count=faces.Extent(),
        solid_face_count=solid_faces.Extent(),
        non_solid_face_count=non_solid_faces,
        valid=bool(BRepCheck_Analyzer(native, True).IsValid()),
    )


def _mapped_shapes(shape, kind) -> TopTools_IndexedMapOfShape:
    mapped = TopTools_IndexedMapOfShape()
    TopExp.MapShapes_s(shape, kind, mapped)
    return mapped
