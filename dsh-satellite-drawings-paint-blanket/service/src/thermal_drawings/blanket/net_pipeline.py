"""B11 worker-level manufacturing result, independent of B10 enclosed volume."""
import copy
import time
from ..domain.acceptance import aggregate
from ..domain.validation import fingerprint,canonical,validate
from .unfold import unfold
from .overlaps import build_overlaps
from .fixed_points import rebind,edit
from .mapping import foldback
from .net_drawing import drawing

def generate_net(cover,settings=None,point_state=None,point_command=None,output=None):
    started=time.perf_counter()
    feature=cover['parameters'].get('envelope_policy')=='feature_composite_v1'
    if feature and not (settings or {}).get('connection_plan') and not any(k in (settings or {}) for k in ('fold_seam_ids','cut_seam_ids')):
        from .feature_cover import default_settings
        defaults=default_settings(cover['panels'],cover['parameters'].get('feature_overlap_mm',15.))
        defaults.update(copy.deepcopy(settings or {}));settings=defaults
    if (settings or {}).get('connection_plan')=='connected_15mm_v1':
        from .seam_plans import propose
        settings=propose(cover,settings)['settings']
    if feature:print('feature_net stage=unfold',flush=True)
    net=unfold(cover['panels'],settings)
    if cover['parameters'].get('envelope_policy') in ('regular_box_v1','regular_cylinder_v1'):
        from .regular_cover import summary
        from .selection import BlanketError
        counts=summary(cover['parameters'],len(net['pieces']))
        if counts['requirements_unmet']:
            raise BlanketError('piece_limit_exceeded: final cutting pieces per layer exceed configured hard limit')
        net['manufacturing_summary']=counts
        net['regular_envelope']=copy.deepcopy(cover['regular_envelope'])
    if feature:
        from .regular_cover import summary
        net['manufacturing_summary']=summary(cover['parameters'],len(net['pieces']))
        net['feature_composite']=copy.deepcopy(cover['feature_composite'])
    net.update(schema_version=1,revision_id=cover['revision_id'],model_ref=copy.deepcopy(cover['model_ref']),algorithm_version='b11-planar-v1',
               cover_baseline_id=cover['baseline']['id'],cover_checks=copy.deepcopy(cover['checks']))
    mapping_hash=fingerprint(dict(panels=cover['panels'],seams=net['seams'],transforms=[p['transform'] for p in net['panels']]))[:24]
    for p in net['panels']:p['mapping_ref']=f"{cover['revision_id']}:{p['key']}:{mapping_hash}"
    build_overlaps(net)
    if feature and cover['parameters'].get('auto_fixed_points',True):
        from .fixed_points import seed_feature_points
        point_state=seed_feature_points(net,point_state,cover['baseline']['id'])
    state=rebind(net,point_state)
    if point_command:state=edit(net,state,point_command)
    net.update(point_state=state,fixed_points=state['points'])
    for p in state['points']:
        if p['status']!='valid':net['diagnostics'].append(dict(code='fixed_point_needs_reselection',refs=[p['id']],location=p['uv_mm'],candidates=[dict(action='move_or_delete',point_id=p['id'])]))
    net['foldback']=foldback(net)
    technical=not net['diagnostics'] and net['foldback']['status']=='pass'
    for check in net['cover_checks']:
        if check['id']=='piece_limit' and 'manufacturing_summary' in net:
            check.update(observed=copy.deepcopy(net['manufacturing_summary']),status='fail' if net['manufacturing_summary']['requirements_unmet'] else 'pass')
        if check['id']=='unfolding':check.update(status='pass' if technical else 'fail',observed=dict(net_revision=net['revision_id'],foldback=net['foldback']),reason='Matching current net topology and foldback evaluated')
    net['status']='passed' if technical else 'failed'
    net['checks']=[dict(id='net_topology_material',status='pass' if net['status']=='passed' else 'fail',scope_refs=[ref for p in net['panels'] for ref in p['source_refs']],observed=dict(diagnostics=net['diagnostics'],areas=net['areas'],foldback_error_mm=net['foldback']['maximum_error_mm']),limit=None,units='mm',algorithm_version='b11-planar-v1',evidence_refs=[],reason='Full-width tabs, material points and rigid foldback; no manufacturing margin assumed')]
    sphere_widths=[t['surface_width_measurement'] for t in net['overlaps'] if t.get('surface_width_measurement',{}).get('width_metric') in ('native_shortest_great_circle_distance_to_meridian','native_shortest_great_circle_distance_to_seam')]
    if sphere_widths:
        net['checks'].append(dict(id='native_spherical_overlap_width',status='pass',scope_refs=[],observed=dict(tabs=sphere_widths),limit=dict(requested_widths_mm=[t['requested_width_mm'] for t in sphere_widths],numerical_readback_mm=1e-6),units='mm',algorithm_version='b13-native-surface-v1',evidence_refs=[],reason='Requested physical geodesic overlap width constructed with native spherical circles; chart width is compensated. This does not approve material strain.'))
    if cover.get('candidate_editable'):
        net['checks']=copy.deepcopy(net['cover_checks'])+net['checks']
        net['status']=aggregate(net['checks']);net['candidate_editable']=True
    if net['diagnostics'] and not settings and cover.get('candidate_editable'):
        from .seam_plans import propose
        from .panels import NetError
        try:proposal=propose(cover);net['diagnostics'].append(dict(code='connected_seam_plan_available',refs=[],location=None,candidates=[dict(action='apply_explicit_plan',**proposal)]))
        except NetError as error:net['diagnostics'].append(error.diagnostic)
    if feature:print('feature_net stage=drawing elapsed_s='+str(round(time.perf_counter()-started,3)),flush=True)
    net['drawing_document']=drawing(net)
    validate('blanket',net,'NetResult')
    if output is not None:
        from .net_native import write
        write(net,output)
        (output/'blanket-net.json').write_text(canonical(net));(output/'drawing.json').write_text(canonical(net['drawing_document']))
    if feature:print('feature_net stage=complete elapsed_s='+str(round(time.perf_counter()-started,3)),flush=True)
    return net
