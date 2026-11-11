"""Actual target opening loops, regular integral bosses, explicit rib classification."""
import cadquery as cq
from shapely.ops import unary_union
from geometry_core.solid_pairs import build_common_operation, intersect_face_patches
from .selection import LENGTH_EPS, AREA_EPS, PaintError, ring, face_polygon
from .overrides import classification


RIB_MIN_ASPECT_RATIO = 4.0


def projected_bounds(shape, plane):
    """Conservative UV bounds without sampling trimmed curves."""
    bounds = shape.BoundingBox()
    points = [cq.Vector(x, y, z)
              for x in (bounds.xmin, bounds.xmax)
              for y in (bounds.ymin, bounds.ymax)
              for z in (bounds.zmin, bounds.zmax)]
    uv = [plane.uv(point) for point in points]
    return min(p[0] for p in uv), min(p[1] for p in uv), max(p[0] for p in uv), max(p[1] for p in uv)


def bounds_overlap(left, right, tolerance=LENGTH_EPS):
    return (left[2] >= right[0]-tolerance and right[2] >= left[0]-tolerance
            and left[3] >= right[1]-tolerance and right[3] >= left[1]-tolerance)


def projected_aspect_ratio(polygon):
    rectangle = polygon.minimum_rotated_rectangle
    points = list(rectangle.exterior.coords)
    lengths = [((points[i+1][0]-points[i][0])**2+(points[i+1][1]-points[i][1])**2)**.5 for i in range(4)]
    positive = [value for value in lengths if value > LENGTH_EPS]
    return max(positive)/min(positive) if len(positive) == 4 else 1.0


def opening_evidence(target, plane, model, opening, opening_face, budget):
    """Prove a straight void passage to a real opposite-face inner wire.

    Nested exits permit known through counterbores/countersinks. A buried floor
    or an aligned pocket from the back cannot pass the source-solid column test.
    An absent proof is unknown, never an automatic standard hole.
    """
    occ, _, ref = target
    floors, exits = [], []
    opening_bounds = opening.bounds
    for owner, candidate, candidate_ref in model.faces:
        if owner is not occ or candidate.geomType() != 'PLANE' or plane.gap(candidate.Center()) >= -LENGTH_EPS:
            continue
        # A conservative box rejection must precede the 1e-7 chord sampling.
        # Large assemblies can contain many detailed faces on the far side of
        # the same occurrence that cannot possibly classify this opening.
        if not bounds_overlap(projected_bounds(candidate, plane), opening_bounds):
            continue
        budget.consume(pairs=1)
        normal = candidate.normalAt().dot(plane.z)
        if normal > 1-1e-10:
            gap = plane.gap(candidate.Center())
            footprint = intersect_face_patches(opening_face, candidate.translate(plane.z * -gap))
            if not footprint.completed:
                raise PaintError('kernel_opening', footprint.failure_message or 'Could not project opening floor', 'failed')
            polygons = [face_polygon(patch, plane, budget) for patch in footprint.patches]
            polygon = unary_union(polygons) if polygons else None
            if polygon is not None and polygon.area > AREA_EPS:
                floors.append((candidate_ref, polygon))
        if normal > -1+1e-10:
            continue
        for wire in candidate.innerWires():
            if not bounds_overlap(projected_bounds(wire, plane), opening_bounds):
                continue
            exit_face = cq.Face.makeFromWires(wire)
            gap = plane.gap(candidate.Center())
            footprint = intersect_face_patches(opening_face, exit_face.translate(plane.z * -gap))
            if not footprint.completed:
                raise PaintError('kernel_opening', footprint.failure_message or 'Could not project opening exit', 'failed')
            intersection_area = sum(patch.Area() for patch in footprint.patches)
            exit_area = exit_face.Area()
            if intersection_area <= AREA_EPS:
                continue
            if exit_area-intersection_area > max(1e-6,opening.area*1e-6):
                continue
            budget.consume(pairs=1)
            height = -plane.gap(candidate.Center())
            column = cq.Solid.extrudeLinear(wire, [], plane.z*height)
            common = build_common_operation(occ.shape.wrapped, column.wrapped, fuzzy_tolerance_mm=1e-7,run_parallel=False)
            if not common.IsDone():
                raise PaintError('kernel_opening', 'Could not validate opening passage', 'failed')
            value = cq.Shape.cast(common.Shape())
            volume = abs(value.Volume()) if value.Solids() else 0.0
            if volume <= 1e-9:
                exits.append(dict(exit_face_ref=candidate_ref, exit_area_mm2=exit_area,
                                  passage_depth_mm=height, material_intersection_mm3=volume,
                                  classification='through' if abs(exit_area-opening.area)<=max(1e-6,opening.area*1e-6) else 'stepped_or_countersunk_through'))
    return floors, exits


def feature_patches(target, plane, model, params, overrides, budget, diagnose):
    occ, face, ref = target
    patches, facts, extra_domains = [], [], []
    for wire in face.innerWires():
        opening = ring(wire, plane, budget)
        opening_face = cq.Face.makeFromWires(wire)
        adjacent = [(f, r) for o, f, r in model.faces if o is occ and r != ref
                    and any(e.isSame(w) for e in f.Edges() for w in wire.Edges())]
        boundary_points = []
        for adjacent_face, _ in adjacent:
            for edge in adjacent_face.Edges():
                points, _ = edge.sample(0.01)
                budget.consume(points=len(points))
                boundary_points.extend(points)
        raised = any(plane.gap(p) > LENGTH_EPS for p in boundary_points)
        # Closed circular walls have only seam vertices, which still include both heights.
        if not raised:
            floors, exits = opening_evidence(target, plane, model, opening, opening_face, budget)
            # A precise single floor FaceRef can explicitly classify this pocket's
            # mouth policy. A target-face override cannot implicitly cover holes.
            exact_floors = [r for r,p in floors if p.symmetric_difference(opening).area <= max(1e-6,opening.area*1e-6)]
            override = classification(exact_floors[0], overrides) if len(floors)==len(exact_floors)==1 else None
            evidence = dict(method='actual_target_opening_loop', opening_area_mm2=opening.area,
                            classification='verified_through_opening' if exits else 'blind_or_unverified_pocket',
                            passage_proofs=exits, floor_refs=[r for r,_ in floors], override=override)
            facts.append(evidence)
            if not exits:
                if override and override['classification']=='exclude':
                    continue
                if not override or override['classification']!='hole':
                    diagnose('opening_classification_unknown','needs_review',[ref]+[r for r,_ in floors],
                             dict(reason='No verified through passage; precise floor FaceRef and explicit hole/exclude policy required'))
                    continue
            patches.append(dict(geometry=opening, kind='hole', source_refs=[ref]+[r for _,r in adjacent],
                                offset=params['hole_offset_mm'], origin='manual' if override else 'computed', frame=plane.frame(),
                                evidence=evidence))
            if override:
                patches[-1]['source_refs'].append(override['face_ref'])
            continue
        caps = []
        for o, f, r in model.faces:
            if o is not occ or f.geomType() != 'PLANE' or f.normalAt().dot(plane.z) < 1-1e-10 or plane.gap(f.Center()) <= LENGTH_EPS:
                continue
            if not bounds_overlap(projected_bounds(f, plane), opening.bounds):
                continue
            budget.consume(pairs=1)
            p = face_polygon(f, plane, budget)
            if p.intersection(opening).area > AREA_EPS:
                caps.append((f,r,p))
        if len(caps) != 1:
            diagnose('feature_classification_unknown', 'needs_review', [ref], dict(candidate_caps=len(caps)))
            continue
        cap, cap_ref, domain = caps[0]
        override = classification(cap_ref, overrides)
        circular = len(wire.Edges()) == 1 and wire.Edges()[0].geomType() == 'CIRCLE'
        regular = domain.symmetric_difference(opening).area < max(1e-6, opening.area*1e-6)
        aspect_ratio = projected_aspect_ratio(domain)
        kind = override['classification'] if override else ('boss' if circular and regular else
                'rib' if regular and aspect_ratio >= RIB_MIN_ASPECT_RATIO else 'unknown')
        facts.append(dict(source_refs=[ref, cap_ref], classification=kind, override=override,
                          method='raised_target_loop_and_source_cap', height_mm=plane.gap(cap.Center()),
                          projected_aspect_ratio=aspect_ratio, rib_min_aspect_ratio=RIB_MIN_ASPECT_RATIO))
        if kind in ('rib', 'exclude'):
            continue
        if kind != 'boss':
            diagnose('feature_classification_unknown', 'needs_review', [ref, cap_ref], {})
            continue
        # The raised cap has its own actual material and plane; never fill empty holes.
        frame = plane.frame(plane.gap(cap.Center()))
        extra_domains.append(dict(frame=frame, geometry=domain))
        patches.append(dict(geometry=domain, kind='boss', source_refs=[ref, cap_ref], offset=0,
                            origin='manual' if override else 'computed', frame=frame,
                            evidence=facts[-1]))
        if params['boss_additional_offset_mm']:
            patches.append(dict(geometry=opening, kind='boss', source_refs=[ref, cap_ref],
                                offset=params['boss_additional_offset_mm'], origin='manual' if override else 'computed',
                                frame=plane.frame(), evidence=dict(facts[-1], scope='target_base_perimeter')))
    return patches, facts, extra_domains
