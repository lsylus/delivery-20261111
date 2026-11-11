"""Full-equipment planar covers with a conservative positive-clearance proof.

Each native X slab is enclosed by eight support halfspaces in YZ. Expanding
all unit-normal halfspaces (including both X bounds) by c encloses the entire
c-neighbourhood of that slab. Union preserves this inclusion, unlike scaling
about an anchor. Clipping at installation Z=0 adds only an evaluation cap.
The denominator remains the native recess-closed source, never the polyhedron.
"""
import copy
import math
import cadquery as cq
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Common, BRepAlgoAPI_Fuse
from ..domain.validation import validate, canonical, fingerprint
from .selection import Frame, BlanketError, shape_hash, bounds, EPS
from .checks import boolean, record
from .exterior import close_recesses
from .complex_envelopes import panel_faces

ALGORITHM = 'b13-faceted-clearance-v1'
GUARD = 100 * EPS


def native_bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape.wrapped, box, False, True)
    if box.IsVoid() or box.IsOpen():
        raise BlanketError('unbounded_support_geometry')
    return box.Get()


def clip(poly, normal, support):
    result = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        da = sum(x*y for x, y in zip(a, normal)) - support
        db = sum(x*y for x, y in zip(b, normal)) - support
        if da <= 0:
            result.append(a)
        if da < 0 < db or db < 0 < da:
            result.append([a[k] + (b[k]-a[k])*da/(da-db) for k in range(2)])
    return result


def construct(source, clearance, cuts):
    if not math.isfinite(clearance) or not 0 < clearance <= 10:
        raise BlanketError('positive_clearance_range')
    if any(f.geomType() not in ('PLANE', 'CYLINDER', 'CONE', 'SPHERE') for f in source.Faces()):
        raise BlanketError('faceted_support_requires_analytic_fixture_surfaces')
    bb = native_bounds(source)
    if len(cuts) > 7 or cuts != sorted(set(cuts)) or any(not math.isfinite(x) or not bb[0]+EPS < x < bb[3]-EPS for x in cuts):
        raise BlanketError('invalid_native_section_cuts')
    levels = [bb[0], *cuts, bb[3]]
    radius = max(abs(x) for x in bb) + 2*clearance + 10
    pieces, parts, certificate = [], [], []
    for lo, hi in zip(levels, levels[1:]):
        if hi-lo <= 2*GUARD:
            raise BlanketError('native_section_too_thin')
        slab = cq.Solid.makeBox(hi-lo, bb[4]-bb[1]+2, bb[5]-bb[2]+2, cq.Vector(lo, bb[1]-1, bb[2]-1))
        part = boolean(BRepAlgoAPI_Common, source, slab)
        if not part.Solids():
            raise BlanketError('empty_native_section')
        parts.append(part)
        poly = [[-radius, -radius], [radius, -radius], [radius, radius], [-radius, radius]]
        supports = []
        for i in range(8):
            theta = math.pi*i/4
            normal = [math.cos(theta), math.sin(theta)]
            rotated = part.rotate((0, 0, 0), (1, 0, 0), -math.degrees(theta))
            upper = native_bounds(rotated)[4]
            shifted = upper + clearance + GUARD
            poly = clip(poly, normal, shifted)
            supports.append(dict(unit_normal_yz=normal, native_support_upper_mm=upper, cover_support_mm=shifted))
        if len(poly) < 3:
            raise BlanketError('empty_support_polygon')
        wire = cq.Wire.makePolygon([cq.Vector(lo-clearance-GUARD, y, z) for y, z in poly], close=True)
        piece = cq.Solid.extrudeLinear(wire, [], cq.Vector(hi-lo+2*(clearance+GUARD), 0, 0))
        outside = sum(abs(s.Volume()) for s in boolean(BRepAlgoAPI_Cut, part, piece).Solids())
        if outside > 1e-6:
            raise BlanketError('native_section_support_not_containing')
        pieces.append(piece)
        certificate.append(dict(x_interval_mm=[lo, hi], expanded_x_mm=[lo-clearance-GUARD, hi+clearance+GUARD],
                                source_section_volume_mm3=part.Volume(), source_outside_mm3=outside,
                                support_halfspaces=supports, polygon_yz_mm=poly))
    remainder = source
    for part in parts:
        remainder = boolean(BRepAlgoAPI_Cut, remainder, part)
    if sum(abs(s.Volume()) for s in remainder.Solids()) > 1e-6:
        raise BlanketError('native_sections_do_not_cover_source')
    solid = pieces[0]
    for piece in pieces[1:]:
        solid = boolean(BRepAlgoAPI_Fuse, solid, piece)
    b = native_bounds(solid)
    bottom_clip = cq.Solid.makeBox(b[3]-b[0]+2, b[4]-b[1]+2, b[5]+1, cq.Vector(b[0]-1, b[1]-1, 0))
    solid = boolean(BRepAlgoAPI_Common, solid, bottom_clip).clean()
    if not solid.isValid() or len(solid.Solids()) != 1 or any(f.geomType() != 'PLANE' for f in solid.Faces()):
        raise BlanketError('invalid_faceted_cover')
    proof = dict(method='native_support_halfspace_neighbourhood_union', sections=certificate,
                 native_bound_method='BRepBndLib.AddOptimal(useTriangulation=False,useShapeTolerance=True)',
                 requested_clearance_mm=clearance, numerical_inflation_mm=GUARD,
                 conservative_lower_bound_mm=max(0., clearance-10*EPS),
                 statement='Every native slab lies in its support polyhedron. Unit halfspaces expanded by c contain its complete Euclidean c-neighbourhood. The union covers every source slab. Only installation-plane caps are exempt.',
                 geometry_scope='analytic native fixture surfaces; exact planar manufacturing facets, no sampled clearance inference',
                 manufacturing_tolerance=None, manufacturing_approved=False)
    return solid, proof


def generate(parameters, model, revision, output=None, previous=None):
    validate('blanket', parameters)
    from .installation import validate_setup
    validate_setup(parameters,model)
    if parameters['model_ref'] != model.model_ref:
        raise BlanketError('needs_reselection: model mismatch')
    ids = parameters['target_instances']
    selected = [o for o in model.occurrences if o.id in ids]
    if len(ids) != 1 or len(selected) != 1:
        raise BlanketError('faceted_cover_requires_one_complete_equipment')
    if any(parameters[k] for k in ('included_faces', 'excluded_faces', 'cut_edges', 'fold_edges', 'overlaps', 'fixed_points')) or parameters['unfold_base_panel'] is not None:
        raise BlanketError('faceted_cover_requires_full_equipment_and_current_net_settings')
    if parameters.get('dimensions_mm') or parameters.get('surface_options') or parameters['allowance']['factors'] != [1, 1, 1]:
        raise BlanketError('faceted_cover_uses_explicit_clearance_not_scaling')
    options = parameters.get('clearance_options')
    if options is None:
        raise BlanketError('explicit_clearance_options_required')
    frame = Frame(parameters['installation_frame'])
    occurrence = selected[0]
    original_hash = shape_hash(occurrence.shape)
    source = frame.local(occurrence.shape.copy())
    low, _ = bounds(source)
    if not source.isValid() or len(source.Solids()) != 1 or abs(low[2]) > EPS:
        raise BlanketError('faceted_source_or_installation_plane')
    if parameters.get('installation_face'):
        owner, face, _ = model.resolve(parameters['installation_face'])
        face = frame.local(face)
        if owner.id != occurrence.id or face.geomType() != 'PLANE' or abs(face.Center().z) > EPS or face.normalAt().z > -.99:
            raise BlanketError('needs_reselection: installation face')
    base, closure = close_recesses(source)
    identity = dict(model_ref=model.model_ref, instances=ids, frame=parameters['installation_frame'], source_hash=original_hash, algorithm=closure['algorithm'])
    baseline = dict(id='baseline-'+fingerprint(identity), source_revision=revision, algorithm=closure['algorithm'],
                    parameters=dict(identity=identity, closure=closure), closed_shape_ref='baseline.brep', volume_mm3=base.Volume(),
                    openings_closure=['native-bounded-recesses', 'installation-bottom-evaluation-only'], confirmed_revision=revision)
    if previous and previous['id'] == baseline['id']:
        expected = copy.deepcopy(baseline)
        expected.update(source_revision=previous['source_revision'], confirmed_revision=previous['confirmed_revision'])
        if canonical(expected) != canonical(previous):
            raise BlanketError('baseline_integrity')
        baseline = copy.deepcopy(previous)
    solid, proof = construct(source, options['clearance_mm'], options['section_cuts_mm'])
    refs = occurrence.refs
    panels, native, caps = panel_faces(solid, frame, revision, refs, list(zip(source.Faces(), refs)), parameters)
    outside = sum(abs(s.Volume()) for s in boolean(BRepAlgoAPI_Cut, source, solid).Solids())
    ratio = solid.Volume()/base.Volume()
    gaps = [dict(panel_key=p['key'], lower_bound_mm=proof['conservative_lower_bound_mm'], method=proof['method']) for p in panels]
    checks = [record('volume_ratio', 1 <= ratio <= 1.2, dict(ratio=ratio, cover_volume_mm3=solid.Volume(), baseline_volume_mm3=base.Volume()), 'Fixed native recess-closed baseline; neither support facets nor clearance alter the denominator'),
              record('coverage', outside <= 1e-6, dict(outside_volume_mm3=outside, source_faces=len(source.Faces()), source_instances=ids), 'Entire original occurrence inside evaluation solid'),
              record('positive_clearance', proof['conservative_lower_bound_mm'] > 0, dict(panels=gaps, proof=proof), 'Full-support neighbourhood construction proves a positive bound for every manufacturing face; cap excluded'),
              record('penetration', proof['conservative_lower_bound_mm'] > 0 and outside <= 1e-6, dict(clearance_lower_bound_mm=proof['conservative_lower_bound_mm']), 'Manufacturing facets lie on the exterior of the containing clearance neighbourhood'),
              record('topology', all(f.isValid() for f in native), dict(manufacturing_faces=len(native), evaluation_caps=[n for n, _ in caps]), 'Native planar facets and separate evaluation caps'),
              record('manufacturing_approval', True, dict(clearance_mm=options['clearance_mm'], opening_ids=[o['id'] for o in parameters['openings']], manufacturing_tolerance=None), 'Explicit geometry candidate; engineering opening and clearance approval pending'),
              record('unfolding', True, dict(state='requires_current_net'), 'A current connected net is required')]
    for check in checks:
        check['algorithm_version'] = ALGORITHM
        if check['id'] == 'manufacturing_approval': check['status'] = 'needs_review'
        if check['id'] == 'unfolding': check['status'] = 'not_run'
    lo, hi = bounds(solid)
    result = dict(schema_version=1, revision_id=revision, model_ref=copy.deepcopy(model.model_ref), parameters=copy.deepcopy(parameters), baseline=baseline,
                  dimensions_mm=[b-a for a, b in zip(lo, hi)], panels=panels, native_shape_ref='manufacturing.brep', evaluation_shape_ref='evaluation.brep', display_ref='cover.glb',
                  closures=[dict(id=n, shape_ref=f'closures/{i}.brep', evaluation_only=True) for i, (n, _) in enumerate(caps)], checks=checks,
                  status='failed' if any(c['status']=='fail' for c in checks) else 'needs_review', candidate_editable=True, algorithm_version=ALGORITHM,
                  downstream=dict(revision_id=revision, panels='candidates', unfolding='not_computed', checks_revision=revision))
    validate('blanket', result, 'BlanketResult')
    if shape_hash(occurrence.shape) != original_hash:
        raise BlanketError('source_mutated')
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        for folder in ('panels', 'closures'): (output/folder).mkdir(exist_ok=True)
        frame.world(base).exportBrep(str(output/'baseline.brep'))
        frame.world(solid).exportBrep(str(output/'evaluation.brep'))
        cq.Compound.makeCompound([frame.world(f) for f in native]).exportBrep(str(output/'manufacturing.brep'))
        assembly = cq.Assembly()
        for panel, face in zip(panels, native):
            face = frame.world(face)
            face.exportBrep(str(output/panel['surface_ref']))
            assembly.add(face, name=panel['id'].replace(':', '_'), color=cq.Color(.75, .65, .25))
        for i, (_, face) in enumerate(caps): frame.world(face).exportBrep(str(output/f'closures/{i}.brep'))
        assembly.export(str(output/'cover.glb'))
        from .display import normalize
        normalize(output/'cover.glb', panels)
        (output/'clearance-certificate.json').write_text(canonical(proof))
        (output/'blanket-result.json').write_text(canonical(result))
    return result
