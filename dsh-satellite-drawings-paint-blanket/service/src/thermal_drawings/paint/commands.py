"""Bounded B09 commands. HTTP, controls and MCP share this server validator."""
import copy
import math
from shapely.geometry import Polygon
from ..domain.errors import require


def polygon(points):
    require(isinstance(points, list) and 3 <= len(points) <= 512, message='Select a polygon with 3..512 vertices')
    require(all(isinstance(p, list) and len(p) == 2 and all(type(n) in (int, float) and math.isfinite(n) and abs(n) <= 1e7 for n in p) for p in points), message='Finite drawing-local mm coordinates required')
    p = Polygon(points)
    require(p.is_valid and p.area > 1e-9, message='Polygon must be simple with positive area')
    return p


def point(value):
    require(isinstance(value, list) and len(value) == 2 and all(type(n) in (int, float) and math.isfinite(n) and abs(n) <= 1e7 for n in value), message='Finite local mm point required')


def validate_command(operation, params):
    require(isinstance(params, dict))
    if operation == 'paint.edit_regions':
        action = params.get('action')
        fields = {'result_id', 'action', 'reason'} | ({'region_id', 'delta_mm'} if action == 'move' else {'points'})
        require(action in ('add', 'exclude', 'move') and set(params) == fields, message='Use add/exclude polygon or move region')
        require(isinstance(params['reason'], str) and 0 < len(params['reason'].strip()) <= 500)
        if action == 'move':
            point(params['delta_mm'])
            require(isinstance(params['region_id'], str) and bool(params['region_id']))
        else:
            polygon(params['points'])
    elif operation == 'drawing.edit_annotation':
        require(set(params) == {'result_id', 'annotation_id', 'text', 'position'}, message='Annotation requires ID, text and position')
        require(isinstance(params['annotation_id'], str) and 0 < len(params['annotation_id']) <= 80)
        require(isinstance(params['text'], str) and 0 < len(params['text']) <= 500 and not any(c in params['text'] for c in '\n\r\x00'))
        point(params['position'])
    elif operation == 'drawing.export':
        single = set(params) in ({'result_id', 'draft'}, {'result_id', 'draft', 'preview'})
        batch = set(params) == {'batch_result_id', 'draft'}
        require((single or batch) and params['draft'] is True, message='Only explicitly acknowledged single or batch draft DWG export is available')
        require('preview' not in params or type(params['preview']) is bool, message='Preview must be a boolean')
    elif operation in ('history.undo', 'history.redo'):
        require(params == {}, message='History takes no parameters')
    if 'result_id' in params:
        require(isinstance(params['result_id'], str) and bool(params['result_id']))
    if 'batch_result_id' in params:
        require(isinstance(params['batch_result_id'], str) and bool(params['batch_result_id']))


def prepare_edit(operation, params, paint, revision):
    """Resolve IDs once against exact source bytes; persist geometric intent for replay."""
    require(paint['drawing_document'] is not None, 409, 'result_unavailable')
    command = copy.deepcopy(params)
    command['operation'] = operation
    command['model_ref'] = revision['model_ref']
    command['frame'] = paint['drawing_document']['frame']
    if params.get('action') == 'move':
        region = next((r for r in paint['regions'] if r['id'] == params['region_id']), None)
        require(region is not None, 409, 'needs_reselection', 'Region does not belong to this result')
        require(region['local_frame'] == command['frame'], 422, 'unsupported_frame', 'Move supports regions in the selected drawing plane')
        command['loops'] = region['loops']
    domains=paint.get('evidence',[{}])[0].get('surface_domains',[]) if paint.get('evidence') else []
    if domains and operation=='paint.edit_regions':
        def material(d):return Polygon(d['material_loops'][0]['points'],[l['points'] for l in d['material_loops'][1:]])
        if params.get('action')=='move':matches=[d for d in domains if d['surface_mapping']==region.get('surface_mapping')]
        else:matches=[d for d in domains if material(d).intersection(Polygon(params['points'])).area>1e-9]
        require(len(matches)==1,422,'ambiguous_surface_chart','Select material in exactly one displayed surface chart')
        d=matches[0];command.update(surface_mapping=copy.deepcopy(d['surface_mapping']),material_loops=copy.deepcopy(d['material_loops']),surface_source_refs=copy.deepcopy(d['source_refs']))
    return command
