"""Replay explicit local-mm edits on the same result used by 2D, 3D and DWG."""
import copy
from shapely.geometry import Polygon
from shapely.ops import unary_union
from shapely.affinity import translate
from ..domain.errors import require
from ..domain.validation import validate
from ..paint.selection import polygons, loops
from ..paint.pipeline import unique


def geometry(value):
    return Polygon(value[0]['points'], [v['points'] for v in value[1:]])


def rebind(paint, revision):
    paint = copy.deepcopy(paint)
    old = paint['revision_id']
    paint['revision_id'] = revision
    doc = paint['drawing_document']
    if doc:
        doc['id'] = 'paint-drawing-' + revision
        doc['revision_id'] = revision
        for e in doc['entities']:
            e['id'] = e['id'].replace(old, revision)
    for r in paint['regions']:
        r['id'] = r['id'].replace(old, revision)
    for r in paint['overlay']:
        r['region_id'] = r['region_id'].replace(old, revision)
    return paint


def apply_edits(paint, revision):
    if not revision['document_edits'] or paint['drawing_document'] is None:
        return paint
    paint = copy.deepcopy(paint)
    doc = paint['drawing_document']
    # Outline orientation is defined by B08 (outer CCW, material holes CW).
    material = Polygon()
    outlines = [e['points'] for e in doc['entities'] if e['layer'] == 'OUTLINE']
    for pts in outlines:
        area2 = sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(pts,pts[1:]+pts[:1]))
        if area2 > 0:
            material = material.union(Polygon(pts))
    for pts in outlines:
        area2 = sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(pts,pts[1:]+pts[:1]))
        if area2 < 0:
            material = material.difference(Polygon(pts))
    annotations = {}
    for command in revision['document_edits']:
        require(command.get('model_ref') == paint['model_ref'] and command.get('frame') == doc['frame'], 409, 'needs_reselection', 'Cannot replay edits across a model or plane change')
        if command['operation'] == 'drawing.edit_annotation':
            annotations[command['annotation_id']] = command
            continue
        action = command['action']
        region_shape = geometry(command['loops']) if action == 'move' else Polygon(command['points'])
        additions = region_shape if action == 'add' else translate(region_shape, *command['delta_mm']) if action == 'move' else Polygon()
        selected_material=geometry(command['material_loops']) if command.get('material_loops') else material
        additions = additions.intersection(selected_material)
        if action in ('add', 'move'):
            require(not additions.is_empty, 422, 'empty_edit', 'Protection must intersect selected material')
        changed = []
        for r in paint['regions']:
            g = geometry(r['loops'])
            original = g
            if r['local_frame'] == doc['frame'] and (not command.get('surface_mapping') or r.get('surface_mapping')==command['surface_mapping']):
                if action in ('exclude', 'move'):
                    g = g.difference(region_shape)
                # Avoid overlapping manual hatch with existing protection.
                additions = additions.difference(g)
            if not g.equals(original):
                r = dict(r,origin='manual',provenance=r.get('provenance',[])+[dict(kind='manual',source_refs=revision['selection'],evidence={'command':command})])
            for p in polygons(g):
                changed.append(dict(r, loops=loops(p), area_mm2=p.area))
        for p in polygons(additions):
            changed.append(dict(kind='manual', source_refs=command.get('surface_source_refs',revision['selection']), local_frame=doc['frame'], loops=loops(p),
                protected=True, origin='manual', confidence=1.0, check_refs=[c['id'] for c in paint['checks']],
                area_mm2=p.area, contributor_kinds=['manual'], provenance=[dict(kind='manual', source_refs=revision['selection'], evidence={'command':command})]))
        if paint.get('surface_mapping'):
            for region in changed:region.setdefault('surface_mapping',copy.deepcopy(command.get('surface_mapping',paint['surface_mapping'])))
        paint['regions'] = changed
    doc['entities'] = [e for e in doc['entities'] if e['kind'] not in ('hatch', 'text')]
    paint['overlay'] = []
    for i,r in enumerate(paint['regions']):
        r['id'] = f'paint-region-{revision["id"]}-{i+1}'
        doc['entities'].append(dict(id=r['id'],kind='hatch',layer='PROTECTION',source_refs=r['source_refs'],outer_loop=r['loops'][0],holes=r['loops'][1:],pattern='ANSI31'))
        f=r['local_frame']
        world=[[[f['origin'][i]+p[0]*f['x_axis'][i]+p[1]*f['y_axis'][i] for i in range(3)] for p in l['points']] for l in r['loops']]
        if r.get('surface_mapping'):
            from ..blanket.surface_charts import world as surface_world
            world=[[surface_world(r['surface_mapping'],p) for p in l['points']] for l in r['loops']]
        paint['overlay'].append(dict(region_id=r['id'],source_refs=r['source_refs'],loops_world_mm=world))
    if annotations:
        doc['layers'].append(dict(name='TEXT',color=7,line_type='CONTINUOUS'))
        for key,a in annotations.items():
            doc['entities'].append(dict(id=f'annotation-{revision["id"]}-{key}',kind='text',layer='TEXT',source_refs=revision['selection'],position=a['position'],text=a['text'],height_mm=2.5))
    doc['source_links']=unique([r for e in doc['entities'] for r in e['source_refs']])
    validate('paint',paint,'PaintResult')
    from .document import DrawingDocument
    DrawingDocument(doc)
    return paint
