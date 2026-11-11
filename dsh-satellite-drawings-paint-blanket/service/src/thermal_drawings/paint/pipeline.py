"""One immutable result is the source for both drawing and world-space overlay."""
from shapely.geometry import Polygon
from shapely.ops import unary_union
from ..domain.validation import validate, canonical
from .selection import Budget, Plane, PaintError, Model, Occurrence, face_polygon, polygons, loops, CHORD, LENGTH_EPS
from .overrides import resolve_overrides
from .contacts import contact_patches, contact_pair_budget
from .features import feature_patches
from .offsets import protect, QUAD_SEGS
from .checks import check, VERSION


def unique(values):
    return list({canonical(v): v for v in values}.values())


def generate(params, model, revision_id, *, budget=None, output=None):
    validate('paint', params)
    result = dict(schema_version=1, revision_id=revision_id, model_ref=params['model_ref'], status='failed',
                  regions=[], diagnostics=[], checks=[], drawing_document=None, overlay=[], evidence=[],
                  numerical_policy=dict(chord_mm=CHORD, gap_uncertainty_mm=LENGTH_EPS, offset_quad_segments=QUAD_SEGS,
                                        manufacturing_tolerance=False), algorithm_version=VERSION)

    def diagnose(code, status, refs, observed):
        c = check(code, status, refs, observed, len(result['checks'])+1)
        result['checks'].append(c)
        if status != 'pass':
            result['diagnostics'].append(dict(code=code, status=status, source_refs=refs, observed=observed))

    try:
        # Native projection/sampling may update OCCT caches; never operate on retained input topology.
        model = Model(model.model_ref, [Occurrence(o.id, o.shape.copy(), o.refs) for o in model.occurrences])
        if model.model_ref != params['model_ref']:
            raise PaintError('needs_reselection', 'Input model does not match loaded BRep')
        targets = [model.resolve(ref) for ref in params['target_face_refs']]
        if len(unique(params['target_face_refs'])) != len(targets):
            raise PaintError('duplicate_target', 'Duplicate target selection')
        if any(face.geomType()!='PLANE' for _,face,_ in targets):
            from .surface_pipeline import generate as native_generate
            return native_generate(params,model,revision_id,budget=budget or Budget(),output=output)
        plane = Plane(targets[0][1])
        for _, face, _ in targets:
            other = Plane(face)
            if other.z.dot(plane.z) < 1-1e-10 or abs(plane.gap(other.origin)) > LENGTH_EPS:
                raise PaintError('noncoplanar_targets', 'Select one oriented coplanar surface group per result')
        budget = budget or Budget(maximum_pairs=contact_pair_budget(targets, model, params))
        overrides = resolve_overrides(params['overrides'], model)
        scope = params['scope_boundary']
        scope = Polygon(scope['points']) if scope else None
        if scope is not None and (not scope.is_valid or scope.is_empty or scope.area <= 1e-9):
            raise PaintError('invalid_scope', 'Scope must be a simple positive-area polygon', 'failed')
        material = unary_union([face_polygon(t[1], plane, budget) for t in targets])
        material = material.intersection(scope) if scope is not None else material
        if material.is_empty:
            raise PaintError('empty_scope', 'No selected material in scope')
        patches, extra = [], []
        for target in targets:
            c, evidence = contact_patches(target, plane, model, params, overrides, budget, diagnose)
            f, feature_evidence, domains = feature_patches(target, plane, model, params, overrides, budget, diagnose)
            patches += c+f
            extra += domains
            result['evidence'] += evidence+feature_evidence
        used_overrides = {canonical(e['override']) for e in result['evidence'] if e.get('override')}
        for value in params['overrides']:
            if canonical(value) not in used_overrides:
                diagnose('override_not_applicable', 'needs_review', [value['face_ref']], {'override_id':value['id']})
        domains = [dict(frame=plane.frame(), geometry=material)]
        for d in extra:
            geom = d['geometry'].intersection(scope) if scope is not None else d['geometry']
            existing = next((x for x in domains if x['frame'] == d['frame']), None)
            if existing is None:
                domains.append(dict(frame=d['frame'], geometry=geom))
            else:
                existing['geometry'] = unary_union([existing['geometry'],geom])
        groups = protect(patches, domains, budget)
        entities = []
        for p in polygons(material):
            for loop in loops(p):
                entities.append(dict(id=f'outline-{revision_id}-{len(entities)+1}', kind='polyline', layer='OUTLINE',
                                     source_refs=params['target_face_refs'], points=loop['points'], closed=True))
        for group in groups:
            for poly in polygons(group['geometry']):
                contributors = group['contributors']
                refs = unique([r for c in contributors for r in c['source_refs']])
                kinds = sorted(set(c['kind'] for c in contributors))
                region = dict(id=f'paint-region-{revision_id}-{len(result["regions"])+1}', kind=kinds[0] if len(kinds) == 1 else 'manual',
                              source_refs=refs, local_frame=group['frame'], loops=loops(poly), protected=True,
                              origin='manual' if any(c['origin']=='manual' for c in contributors) else 'computed',
                              confidence=1.0, check_refs=[], area_mm2=poly.area, contributor_kinds=kinds,
                              provenance=[dict(kind=c['kind'], source_refs=c['source_refs'], evidence=c['evidence']) for c in contributors])
                result['regions'].append(region)
                entities.append(dict(id=region['id'], kind='hatch', layer='PROTECTION', source_refs=refs,
                                     outer_loop=region['loops'][0], holes=region['loops'][1:], pattern='ANSI31'))
                frame = region['local_frame']
                world = [[[frame['origin'][i]+uv[0]*frame['x_axis'][i]+uv[1]*frame['y_axis'][i] for i in range(3)]
                          for uv in loop['points']] for loop in region['loops']]
                result['overlay'].append(dict(region_id=region['id'], source_refs=refs, loops_world_mm=world))
        diagnose('planar_scan_complete', 'pass', params['target_face_refs'], dict(pairs=budget.pairs, sampled_points=budget.points))
        for region in result['regions']:
            region['check_refs'] = [c['id'] for c in result['checks']]
        result['drawing_document'] = dict(schema_version=1, id='paint-drawing-'+revision_id, revision_id=revision_id,
            units='mm', frame=plane.frame(), layers=[dict(name='OUTLINE',color=7,line_type='CONTINUOUS'),dict(name='PROTECTION',color=1,line_type='CONTINUOUS')],
            entities=entities, source_links=unique([r for e in entities for r in e['source_refs']]))
        result['status'] = 'failed' if any(c['status']=='fail' for c in result['checks']) else 'needs_review' if result['diagnostics'] else 'passed'
    except Exception as exc:
        error = exc if isinstance(exc, PaintError) else PaintError('kernel_failure', str(exc), 'failed')
        observed = dict(error.observed)
        observed.setdefault('message', str(error))
        diagnose(error.code, 'fail' if error.status=='failed' else 'needs_review',
                 error.source_refs or params['target_face_refs'], observed)
        result.update(status=error.status, regions=[], overlay=[], drawing_document=None)
    validate('paint', result, 'PaintResult')
    return result
