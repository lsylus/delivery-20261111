"""Opposed planar faces, solid penetration and normal projection of local patches."""
import math
import cadquery as cq
from geometry_core.solid_pairs import build_common_operation, intersect_face_patches
from .selection import LENGTH_EPS, PaintError, Plane, face_polygon
from .overrides import classification


MIN_DYNAMIC_PAIR_BUDGET = 10000
MAX_DYNAMIC_PAIR_BUDGET = 250000


def _corners(bounds):
    return [cq.Vector(x,y,z)
            for x in (bounds.xmin,bounds.xmax)
            for y in (bounds.ymin,bounds.ymax)
            for z in (bounds.zmin,bounds.zmax)]


def _ranges(shape, plane):
    points = _corners(shape.BoundingBox())
    gaps = [plane.gap(point) for point in points]
    uv = [plane.uv(point) for point in points]
    return (min(gaps),max(gaps)),(min(p[0] for p in uv),max(p[0] for p in uv)),(min(p[1] for p in uv),max(p[1] for p in uv))


def _face_ranges(face, plane):
    vertices = face.Vertices() if face.geomType() == 'PLANE' else []
    if not vertices:
        return _ranges(face, plane)
    points = [vertex.Center() for vertex in vertices]
    gaps = [plane.gap(point) for point in points]
    uv = [plane.uv(point) for point in points]
    return (min(gaps),max(gaps)),(min(p[0] for p in uv),max(p[0] for p in uv)),(min(p[1] for p in uv),max(p[1] for p in uv))


def _shape_gap_bounds(shape, plane):
    """Tight signed-plane bounds for polyhedral and trimmed source topology.

    Projecting a rotated world AABB can straddle a plane even when the shape
    is wholly on one side.  Native vertices avoid that false penetration path;
    the conservative AABB remains the fallback for vertex-free topology.
    """
    vertices = shape.Vertices()
    if not vertices:
        return _ranges(shape, plane)[0]
    gaps = [plane.gap(vertex.Center()) for vertex in vertices]
    return min(gaps), max(gaps)


def _overlap(left, right, tolerance):
    return left[1] >= right[0]-tolerance and right[1] >= left[0]-tolerance


def _target_carrier(owner, target_face):
    matches = [solid for solid in owner.shape.Solids()
               if any(face.isSame(target_face) for face in solid.Faces())]
    if len(matches) != 1:
        raise PaintError('solid_required', 'Target paint face must belong to exactly one valid solid', 'failed')
    return matches[0]


def contact_sources(target, plane, model, params):
    owner, target_face, _ = target
    _, target_u, target_v = _ranges(target_face, plane)
    tolerance = threshold_interval(params['contact_threshold_mm'], LENGTH_EPS)[1]
    result = []
    for occurrence in model.occurrences:
        if occurrence is owner:
            continue
        gaps, source_u, source_v = _ranges(occurrence.shape, plane)
        if gaps[1] < -LENGTH_EPS or gaps[0] > tolerance:
            continue
        if not _overlap(target_u, source_u, tolerance) or not _overlap(target_v, source_v, tolerance):
            continue
        result.append(occurrence)
    return result


def contact_pair_budget(targets, model, params):
    estimate = 0
    for target in targets:
        _target_carrier(target[0], target[1])
        for occurrence in contact_sources(target, Plane(target[1]), model, params):
            # One native target-plane Common plus a bounded per-source-face
            # scan.  A whole-solid Cartesian face scan is unnecessary once a
            # real footprint on the selected target face has been computed.
            estimate += 1 + len(occurrence.shape.Faces())
    return min(MAX_DYNAMIC_PAIR_BUDGET, max(MIN_DYNAMIC_PAIR_BUDGET, estimate))


def threshold_interval(threshold, deviation=0):
    # Compare directly to outward-rounded endpoints, avoiding cancellation in
    # abs(gap-threshold). The ULP guard covers arithmetic rounding, not a change
    # to the business threshold or the stated geometric uncertainty.
    guard = 8*math.ulp(max(1.0, abs(threshold), abs(deviation)))
    width = LENGTH_EPS+deviation
    return threshold-width-guard, threshold+width+guard


def target_plane_patches(target_face, source_shape):
    """Return the positive-area part of source_shape on the selected face.

    The selected face, rather than its complete carrier solid, is the left
    operand.  This both clips the footprint to paintable material and avoids
    reporting unrelated intersections elsewhere in the carrier as paint-plane
    penetration.
    """
    try:
        operation = build_common_operation(target_face.wrapped, source_shape.wrapped,
                                           fuzzy_tolerance_mm=LENGTH_EPS, run_parallel=False)
        if not operation.IsDone():
            return None, 'OCCT target-plane section did not complete'
        native = operation.Shape()
        if native.IsNull():
            return (), None
        shape = cq.Shape.cast(native)
        patches = tuple(face for face in shape.Faces() if face.Area() > 1e-9)
        if any(not face.isValid() for face in patches):
            return None, 'Target-plane section produced invalid topology'
        return patches, None
    except Exception as exc:
        return None, str(exc) or type(exc).__name__


def contact_patches(target, plane, model, params, overrides, budget, diagnose):
    owner, target_face, target_ref = target
    _target_carrier(owner, target_face)
    _, target_u, target_v = _face_ranges(target_face, plane)
    threshold = threshold_interval(params['contact_threshold_mm'], LENGTH_EPS)[1]
    result, facts = [], []
    for occ in contact_sources(target, plane, model, params):
        shell_source = not occ.shape.Solids()
        gaps, _, _ = _ranges(occ.shape, plane)
        actual_gaps = _shape_gap_bounds(occ.shape, plane)
        if shell_source:
            diagnose('shell_contact_source', 'needs_review', [target_ref, occ.refs[0]],
                     dict(face_count=len(occ.shape.Faces()), gap_bounds_mm=list(gaps),
                          volume_check='not_applicable_shell_source'))

        crosses_plane = actual_gaps[0] < -LENGTH_EPS and actual_gaps[1] > LENGTH_EPS
        if crosses_plane:
            budget.consume(pairs=1)
            section, section_error = target_plane_patches(target_face, occ.shape)
            if section_error is not None:
                diagnose('plane_section_invalid', 'needs_review', [target_ref, occ.refs[0]],
                         dict(instance_id=occ.id, message=section_error, gap_bounds_mm=list(actual_gaps)))
                continue
            if section:
                try:
                    geometries = [face_polygon(face, plane, budget) for face in section]
                except PaintError as error:
                    diagnose('plane_section_invalid', 'needs_review', [target_ref, occ.refs[0]],
                             dict(instance_id=occ.id, message=str(error), gap_bounds_mm=list(actual_gaps)))
                    continue
                evidence = dict(source_refs=[target_ref, occ.refs[0]], decision='contact',
                                method='target_plane_section', gap_bounds_mm=list(actual_gaps),
                                gap_mm=0.0, normal_dot=None, common_before_projection=True,
                                patch_areas_mm2=[face.Area() for face in section],
                                offset_mm=params['contact_offset_mm'])
                facts.append(evidence)
                result.extend(dict(geometry=geometry, kind='contact', source_refs=[target_ref, occ.refs[0]],
                                   offset=params['contact_offset_mm'], origin='computed', frame=plane.frame(),
                                   evidence=evidence) for geometry in geometries)
                continue
            if not shell_source:
                # Completed empty Common proves that the source crosses only
                # the infinite plane outside the trimmed paint face.
                continue

        shell_patch_count = 0
        for _, face, ref in [item for item in model.faces if item[0] is occ]:
            budget.consume(pairs=1)
            override = classification(ref, overrides)
            if shell_source:
                face_gaps, source_u, source_v = _face_ranges(face, plane)
                if not _overlap(target_u, source_u, threshold) or not _overlap(target_v, source_v, threshold):
                    continue
                if face_gaps[1] < -LENGTH_EPS or face_gaps[0] > threshold:
                    continue
                if face_gaps[0] < -LENGTH_EPS and face_gaps[1] > LENGTH_EPS:
                    diagnose('plane_section_open', 'needs_review', [target_ref, ref],
                             dict(gap_bounds_mm=list(face_gaps), source_face_ref=ref,
                                  message='Shell crosses the target plane without a closed positive-area footprint'))
                    continue
            if face.geomType() != 'PLANE':
                # A curved source near the target may carry unclassified contact.
                if face.distance(target_face) < params['contact_threshold_mm']:
                    diagnose('curved_contact_unknown', 'needs_review', [target_ref, ref], {})
                continue
            alignment = face.normalAt().dot(plane.z)
            normal_error = min((face.normalAt()+plane.z).Length, (face.normalAt()-plane.z).Length) if shell_source else (face.normalAt()+plane.z).Length
            if normal_error > 1e-10:
                if alignment < -1e-6 and face.distance(target_face) < params['contact_threshold_mm']:
                    diagnose('nonparallel_gap_unknown', 'needs_review', [target_ref, ref], dict(normal_dot=alignment))
                facts.append(dict(source_refs=[target_ref, ref], decision='direction_excluded', normal_dot=alignment))
                continue
            gap = plane.gap(face.Center())
            # Bound local gap over the entire face, not only its centroid. For
            # planar faces the normal mismatch times the full bounding diagonal
            # bounds every point's signed-gap departure from the centroid.
            bbox = face.BoundingBox()
            deviation = normal_error * (bbox.xlen**2+bbox.ylen**2+bbox.zlen**2)**.5
            if deviation > LENGTH_EPS:
                diagnose('nonparallel_gap_unknown', 'needs_review', [target_ref, ref], dict(local_gap_bound_mm=deviation))
                continue
            lower, upper = threshold_interval(params['contact_threshold_mm'], deviation)
            if gap < -LENGTH_EPS or gap > upper:
                continue
            if gap < 0:
                diagnose('signed_gap_uncertain', 'needs_review', [target_ref, ref], dict(gap_mm=gap))
                continue
            if lower <= gap <= upper:
                diagnose('threshold_uncertain', 'needs_review', [target_ref, ref], dict(gap_mm=gap, threshold_mm=params['contact_threshold_mm'], comparison='lt', uncertainty_bounds_mm=[lower,upper]))
                continue
            if gap >= params['contact_threshold_mm']:
                continue
            patch = intersect_face_patches(target_face, face.translate(plane.z * -gap))
            if not patch.completed:
                raise PaintError('kernel_projection', patch.failure_message or 'Projected face intersection failed', 'failed')
            kind = override['classification'] if override else 'contact'
            evidence = dict(source_refs=[target_ref, ref], gap_mm=gap, normal_dot=alignment,
                            local_gap_bounds_mm=[gap-deviation,gap+deviation],
                            projection_direction=list(plane.z.toTuple()), common_before_projection=bool(intersect_checked(target_face, face)),
                            patch_areas_mm2=[f.Area() for f in patch.patches], decision=kind,
                            override=override)
            facts.append(evidence)
            if kind in ('exclude', 'rib'):
                continue
            if kind not in ('contact', 'boss'):
                diagnose('classification_unknown', 'needs_review', [target_ref, ref], {'classification':kind})
                continue
            for f in patch.patches:
                if shell_source:
                    shell_patch_count += 1
                result.append(dict(geometry=face_polygon(f, plane, budget), kind=kind, source_refs=[target_ref, ref],
                                   offset=params['contact_offset_mm'] if kind == 'contact' else params['boss_additional_offset_mm'],
                                   origin='manual' if override else 'computed', frame=plane.frame(), evidence=evidence))
        if shell_source and shell_patch_count == 0:
            diagnose('shell_contact_unresolved', 'needs_review', [target_ref, occ.refs[0]],
                     dict(message='Shell source is near the target but has no verified planar contact footprint'))
    return result, facts


def intersect_checked(a, b):
    value = intersect_face_patches(a, b)
    if not value.completed:
        raise PaintError('kernel_common', value.failure_message or 'Face Common failed', 'failed')
    return value.patches
