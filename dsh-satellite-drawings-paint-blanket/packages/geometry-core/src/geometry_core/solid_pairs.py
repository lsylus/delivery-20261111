"""Neutral OCCT pair facts. Numerical settings are not business tolerances.

Derived from S/backend/geometry/solid_pairs.py at 29fecb3; provenance and
intentional failure-handling differences are in docs/evidence/B03.
Invoke inside a controlled CAD worker. This module assigns no public IDs.
"""
from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass

import cadquery as cq
import numpy as np
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.TopTools import TopTools_ListOfShape

from .bounds import BoundsStrategy, bounds_gap, measure_shape_bounds


class SolidPairMeasurementError(RuntimeError):
    """No successful measurement exists; callers must not substitute zero."""
    completed = False

    def __init__(self, stage: str, message: str):
        super().__init__(message)
        self.stage = stage


@dataclass(frozen=True, slots=True)
class FacePatchIntersection:
    completed: bool
    patches: tuple[cq.Shape, ...]
    failure_stage: str | None = None
    failure_message: str | None = None

    def __post_init__(self):
        if not isinstance(self.completed, bool):
            raise TypeError('completed must be a boolean')
        patches = tuple(self.patches)
        if not all(isinstance(p, cq.Shape) for p in patches):
            raise TypeError('patches must contain CadQuery shapes')
        if not self.completed and patches:
            raise ValueError('incomplete intersections cannot publish patches')
        if self.completed and (self.failure_stage or self.failure_message):
            raise ValueError('completed intersections cannot have a failure')
        object.__setattr__(self, 'patches', patches)


@dataclass(frozen=True, slots=True)
class PlanarContactMeasurement:
    """Area sum over planar face pairs only; None means no positive area known.

    completed concerns this scope, never total curved-surface coverage. A
    budget or kernel failure discards partial area, preserving diagnostics.
    """
    completed: bool
    area_mm2: float | None
    nonplanar_face_count: int = 0
    failure_stage: str | None = None
    failure_message: str | None = None
    scope: str = 'planar_faces'

    def __post_init__(self):
        if not isinstance(self.completed, bool):
            raise TypeError('completed must be a boolean')
        if self.area_mm2 is not None:
            _positive(self.area_mm2, 'planar area')
        if not self.completed and self.area_mm2 is not None:
            raise ValueError('incomplete planar scans cannot publish area')
        if self.completed and (self.failure_stage or self.failure_message):
            raise ValueError('completed scans cannot have a failure')


@dataclass(frozen=True, slots=True)
class SolidPairMeasurement:
    """Successful computation, independent of input topology acceptance.

    A separated pair outside the supplied intersection search limit has
    analytically zero common volume; intersection_performed records the
    early-out. None contact area is unknown/not positive, never a zero-area
    or full-surface coverage certificate.
    """
    distance_mm: float
    intersection_volume_mm3: float
    contact_area_mm2: float | None
    left_valid: bool
    right_valid: bool
    intersection_performed: bool
    completed: bool = True
    contact_scope: str = 'common_faces_or_planar_fallback'

    def __post_init__(self):
        _nonnegative(self.distance_mm, 'distance')
        _nonnegative(self.intersection_volume_mm3, 'intersection volume')
        if self.contact_area_mm2 is not None:
            _positive(self.contact_area_mm2, 'contact area')
        if self.completed is not True:
            raise ValueError('incomplete measurement must use SolidPairMeasurementError')
        if not all(isinstance(v, bool) for v in (self.left_valid, self.right_valid, self.intersection_performed)):
            raise TypeError('validity and operation flags must be booleans')


@dataclass(frozen=True, slots=True)
class OpposedPlanarFaceMeasurement:
    """Positive projected overlap between one separated opposed planar pair."""
    gap_mm: float
    contact_area_mm2: float

    def __post_init__(self):
        _nonnegative(self.gap_mm, 'planar gap')
        _positive(self.contact_area_mm2, 'projected contact area')


@dataclass(frozen=True, slots=True)
class OpposedPlanarContact:
    """Neutral source indices; public face references belong to caller adapters."""
    target_key: str
    target_face_index: int
    support_key: str
    support_face_index: int
    gap_mm: float
    contact_area_mm2: float

    def __post_init__(self):
        if not all(isinstance(value, str) and value for value in (self.target_key, self.support_key)):
            raise ValueError('occurrence keys must be non-empty strings')
        if self.target_key == self.support_key:
            raise ValueError('target and support occurrence keys must differ')
        if not all(isinstance(value, int) and not isinstance(value, bool) and value >= 0
                   for value in (self.target_face_index, self.support_face_index)):
            raise ValueError('face indices must be non-negative integers')
        _nonnegative(self.gap_mm, 'planar gap')
        _positive(self.contact_area_mm2, 'projected contact area')


def _nonnegative(value, name):
    if isinstance(value, bool) or not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f'{name} must be a non-negative finite number')


def _positive(value, name):
    _nonnegative(value, name)
    if float(value) == 0:
        raise ValueError(f'{name} must be a positive finite number')


def _budget(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError('maximum face pairs must be a non-negative integer')


@contextmanager
def _stage(name):
    try:
        yield
    except SolidPairMeasurementError:
        raise
    except Exception as exc:
        raise SolidPairMeasurementError(name, str(exc)) from exc


def build_common_operation(left, right, *, fuzzy_tolerance_mm=None, run_parallel=None):
    """Set non-destructive mode BEFORE any native build; None keeps defaults."""
    if fuzzy_tolerance_mm is not None:
        _positive(fuzzy_tolerance_mm, 'fuzzy tolerance')
    if run_parallel is not None and not isinstance(run_parallel, bool):
        raise ValueError('run_parallel must be a boolean or None')
    operation = BRepAlgoAPI_Common()
    arguments, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
    arguments.Append(left)
    tools.Append(right)
    operation.SetArguments(arguments)
    operation.SetTools(tools)
    operation.SetNonDestructive(True)
    if run_parallel is not None:
        operation.SetRunParallel(run_parallel)
    if fuzzy_tolerance_mm is not None:
        operation.SetFuzzyValue(float(fuzzy_tolerance_mm))
    operation.Build()
    return operation


def _common_operation(left, right, fuzzy):
    return build_common_operation(left, right, fuzzy_tolerance_mm=fuzzy, run_parallel=False)


def intersect_face_patches(left_face, right_face, *, fuzzy_tolerance_mm=1e-7,
                           minimum_patch_area_mm2=1e-7):
    """C04: incomplete / completed empty / completed positive patches.

    Invalid numerical parameters raise ValueError before native execution.
    Native failure returns completed=False with stage, never empty success.
    """
    if fuzzy_tolerance_mm is not None:
        _positive(fuzzy_tolerance_mm, 'fuzzy tolerance')
    _positive(minimum_patch_area_mm2, 'minimum patch area')
    try:
        op = _common_operation(left_face.wrapped, right_face.wrapped, fuzzy_tolerance_mm)
        if not op.IsDone():
            return FacePatchIntersection(False, (), 'face_intersection', 'OCCT face intersection did not complete')
        native = op.Shape()
        if native.IsNull():
            return FacePatchIntersection(True, ())
        patches = []
        for face in cq.Shape.cast(native).Faces():
            area = abs(float(face.Area()))
            _nonnegative(area, 'patch area')
            if area > float(minimum_patch_area_mm2):
                patches.append(face)
        return FacePatchIntersection(True, tuple(patches))
    except Exception as exc:
        return FacePatchIntersection(False, (), 'face_intersection', str(exc))


def measure_opposed_planar_face_contact(target_face, support_face, *, maximum_gap_mm=.1,
                                         minimum_contact_area_mm2=1e-7,
                                         normal_alignment_tolerance=1e-10,
                                         numerical_gap_tolerance_mm=1e-7):
    """Measure a real native overlap after normal translation to the target plane.

    ``maximum_gap_mm`` is an inclusive caller policy. The numerical gap tolerance
    only clamps kernel/rigid-transform noise at zero; it never extends that upper
    business limit. A materially negative signed gap is penetration, not contact.
    """
    _nonnegative(maximum_gap_mm, 'maximum gap')
    _positive(minimum_contact_area_mm2, 'minimum contact area')
    _nonnegative(normal_alignment_tolerance, 'normal alignment tolerance')
    if float(normal_alignment_tolerance) >= 1:
        raise ValueError('normal alignment tolerance must be in [0, 1)')
    _nonnegative(numerical_gap_tolerance_mm, 'numerical gap tolerance')
    if target_face.geomType() != 'PLANE' or support_face.geomType() != 'PLANE':
        return None
    target_normal = np.asarray(target_face.normalAt().toTuple(), dtype=float)
    support_normal = np.asarray(support_face.normalAt().toTuple(), dtype=float)
    if not np.isfinite(target_normal).all() or not np.isfinite(support_normal).all():
        raise SolidPairMeasurementError('planar_normal', 'nonfinite planar normal')
    target_length, support_length = np.linalg.norm(target_normal), np.linalg.norm(support_normal)
    if target_length == 0 or support_length == 0:
        raise SolidPairMeasurementError('planar_normal', 'zero planar normal')
    target_normal /= target_length
    support_normal /= support_length
    if float(target_normal @ support_normal) > -1 + float(normal_alignment_tolerance):
        return None
    centers = np.asarray(support_face.Center().toTuple()) - np.asarray(target_face.Center().toTuple())
    gap = float(centers @ target_normal)
    if not math.isfinite(gap):
        raise SolidPairMeasurementError('planar_gap', 'nonfinite planar gap')
    if gap < -float(numerical_gap_tolerance_mm):
        return None
    if gap < 0:
        gap = 0.0
    maximum = float(maximum_gap_mm)
    upper_guard = 8 * math.ulp(max(1.0, abs(maximum)))
    if gap > maximum + upper_guard:
        return None
    if gap > maximum:
        gap = maximum
    projected = support_face.translate(cq.Vector(*target_normal) * -gap)
    intersection = intersect_face_patches(
        target_face, projected, minimum_patch_area_mm2=minimum_contact_area_mm2)
    if not intersection.completed:
        raise SolidPairMeasurementError(
            intersection.failure_stage or 'face_intersection',
            intersection.failure_message or 'OCCT face projection intersection did not complete')
    area = sum(abs(float(face.Area())) for face in intersection.patches)
    _nonnegative(area, 'projected contact area')
    if area <= float(minimum_contact_area_mm2):
        return None
    return OpposedPlanarFaceMeasurement(gap, area)


def find_opposed_planar_contacts(target_key, target_shape, supports, *, maximum_gap_mm=.1,
                                  minimum_contact_area_mm2=1e-7,
                                  normal_alignment_tolerance=1e-10):
    """Return deterministic face-pair facts for world-space occurrence shapes."""
    _nonnegative(maximum_gap_mm, 'maximum gap')
    if not isinstance(target_key, str) or not target_key:
        raise ValueError('target key must be a non-empty string')
    if not isinstance(target_shape, cq.Shape):
        raise TypeError('target shape must be a CadQuery shape')
    support_rows = list(supports)
    keys = [row[0] for row in support_rows]
    if any(not isinstance(key, str) or not key for key in keys) or len(keys) != len(set(keys)):
        raise ValueError('support keys must be unique non-empty strings')
    if target_key in keys:
        raise ValueError('target occurrence cannot also be a support')
    if any(not isinstance(shape, cq.Shape) for _, shape in support_rows):
        raise TypeError('support shapes must be CadQuery shapes')
    result = []
    target_faces = target_shape.Faces()
    support_faces = [(key, shape.Faces()) for key, shape in support_rows]
    for target_index, target_face in enumerate(target_faces):
        if target_face.geomType() != 'PLANE':
            continue
        for support_key, faces in support_faces:
            for support_index, support_face in enumerate(faces):
                measured = measure_opposed_planar_face_contact(
                    target_face, support_face, maximum_gap_mm=maximum_gap_mm,
                    minimum_contact_area_mm2=minimum_contact_area_mm2,
                    normal_alignment_tolerance=normal_alignment_tolerance)
                if measured is not None:
                    result.append(OpposedPlanarContact(
                        target_key, target_index, support_key, support_index,
                        measured.gap_mm, measured.contact_area_mm2))
    return tuple(result)


def _bounds(shape):
    return measure_shape_bounds(shape.wrapped, strategy=BoundsStrategy.OPTIMAL_WITH_SHAPE_TOLERANCE).values


def measure_planar_contact_area(left, right, *, fuzzy_tolerance_mm=1e-7,
                                minimum_contact_area_mm2=1e-7,
                                bounds_gap_tolerance_mm=1e-5,
                                normal_alignment_tolerance=1e-7,
                                maximum_face_pairs=100_000):
    """Source planar scan with explicit budget/failure state, no partial area."""
    _positive(fuzzy_tolerance_mm, 'fuzzy tolerance')
    _positive(minimum_contact_area_mm2, 'minimum contact area')
    _nonnegative(bounds_gap_tolerance_mm, 'bounds gap tolerance')
    _nonnegative(normal_alignment_tolerance, 'normal alignment tolerance')
    if float(normal_alignment_tolerance) >= 1:
        raise ValueError('normal alignment tolerance must be in [0, 1)')
    _budget(maximum_face_pairs)
    nonplanar = 0
    try:
        left_faces, right_faces = left.Faces(), right.Faces()
        nonplanar = sum(f.geomType() != 'PLANE' for f in left_faces + right_faces)
        if len(left_faces) * len(right_faces) > maximum_face_pairs:
            return PlanarContactMeasurement(False, None, nonplanar, 'planar_budget', 'face-pair budget exceeded')
        area = 0.0
        for a in left_faces:
            if a.geomType() != 'PLANE':
                continue
            normal = np.asarray(a.normalAt().toTuple(), dtype=float)
            bounds = _bounds(a)
            for b in right_faces:
                if b.geomType() != 'PLANE' or bounds_gap(bounds, _bounds(b)) > float(bounds_gap_tolerance_mm):
                    continue
                other = np.asarray(b.normalAt().toTuple(), dtype=float)
                if not np.isfinite(normal).all() or not np.isfinite(other).all():
                    raise ValueError('nonfinite planar normal')
                if abs(float(normal @ other)) < 1 - float(normal_alignment_tolerance):
                    continue
                r = intersect_face_patches(a, b, fuzzy_tolerance_mm=fuzzy_tolerance_mm,
                                           minimum_patch_area_mm2=minimum_contact_area_mm2)
                if not r.completed:
                    return PlanarContactMeasurement(False, None, nonplanar,
                                                    r.failure_stage or 'face_intersection', r.failure_message)
                area += sum(abs(float(f.Area())) for f in r.patches)
                _nonnegative(area, 'planar area')
        return PlanarContactMeasurement(True, area if area > float(minimum_contact_area_mm2) else None, nonplanar)
    except Exception as exc:
        return PlanarContactMeasurement(False, None, nonplanar, 'planar_contact', str(exc))


def measure_shape_pair(left, right, *, intersection_distance_limit_mm,
                       zero_volume_tolerance_mm3, fuzzy_tolerance_mm=1e-7,
                       minimum_contact_area_mm2=1e-7, maximum_planar_face_pairs=100_000):
    """Distance/common volume, common-face area or planar fallback.

    Settings remain caller supplied. A successful computation is not an
    approval of invalid topology. All kernel errors carry stage and propagate;
    unknown/partial work is never represented by a successful zero.
    """
    _nonnegative(intersection_distance_limit_mm, 'intersection distance limit')
    _nonnegative(zero_volume_tolerance_mm3, 'zero-volume tolerance')
    _positive(fuzzy_tolerance_mm, 'fuzzy tolerance')
    _positive(minimum_contact_area_mm2, 'minimum contact area')
    _budget(maximum_planar_face_pairs)
    with _stage('input_validity'):
        if left.wrapped.IsNull() or right.wrapped.IsNull():
            raise ValueError('cannot measure a null input shape')
        left_valid = bool(BRepCheck_Analyzer(left.wrapped, True).IsValid())
        right_valid = bool(BRepCheck_Analyzer(right.wrapped, True).IsValid())
    with _stage('distance'):
        op = BRepExtrema_DistShapeShape(left.wrapped, right.wrapped)
        op.SetMultiThread(False)
        op.Perform()
        if not op.IsDone():
            raise SolidPairMeasurementError('distance', 'OCCT distance calculation did not complete')
        distance = float(op.Value())
        _nonnegative(distance, 'distance')
    volume, area = 0.0, None
    performed = distance <= float(intersection_distance_limit_mm)
    if performed:
        with _stage('intersection'):
            op = _common_operation(left.wrapped, right.wrapped, fuzzy_tolerance_mm)
            if not op.IsDone():
                raise SolidPairMeasurementError('intersection', 'OCCT solid intersection did not complete')
            native = op.Shape()
            if not native.IsNull():
                common = cq.Shape.cast(native)
                # A sheet is not a volume; CadQuery Volume() on it is not used.
                volume = abs(float(common.Volume())) if common.Solids() else 0.0
                _nonnegative(volume, 'intersection volume')
                faces = common.Faces()
                if faces and volume <= float(zero_volume_tolerance_mm3):
                    area = sum(abs(float(f.Area())) for f in faces)
                    _nonnegative(area, 'contact area')
        if volume <= float(zero_volume_tolerance_mm3) and (area is None or area <= float(minimum_contact_area_mm2)):
            with _stage('planar_contact'):
                r = measure_planar_contact_area(left, right, fuzzy_tolerance_mm=fuzzy_tolerance_mm,
                                               minimum_contact_area_mm2=minimum_contact_area_mm2,
                                               maximum_face_pairs=maximum_planar_face_pairs)
                if not r.completed:
                    raise SolidPairMeasurementError(r.failure_stage or 'planar_contact', r.failure_message or 'planar scan incomplete')
                area = r.area_mm2
    return SolidPairMeasurement(distance, volume, area, left_valid, right_valid, performed)
