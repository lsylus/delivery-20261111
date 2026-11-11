"""Versioned net commands, with durable ID reservations across undo/restore branches."""
import copy
import json
import math
import uuid
from ..domain.errors import require
from ..domain.validation import validate
from ..storage.assets import controlled,sha

OPERATIONS=('blanket.unfold','blanket.edit_seams','blanket.edit_fixed_points')

def current_net(repo,c,project,revision,result_id=None,optional=False):
    rows=c.execute("SELECT a.body,r.state FROM artifacts a JOIN runs r ON json_extract(a.body,'$.run_id')=r.id WHERE a.project=? AND a.module='blanket' ORDER BY a.rowid DESC",(project,)).fetchall()
    for row in rows:
        a=json.loads(row['body'])
        if row['state']!='succeeded' or a['role']!='blanket_net' or a['revision_id']!=revision or (result_id is not None and a['run_id']!=result_id):continue
        path=controlled(repo.root,a['relative_storage_path']);require(path.is_file() and sha(path)==a['sha256'],409,'integrity_failed')
        value=json.loads(path.read_text());validate('blanket',value,'NetResult');require(value['revision_id']==revision,409,'result_conflict')
        return dict(result_id=a['run_id'],net=value,artifact=a)
    if optional:return None
    require(False,409,'result_conflict','Exact current unfolded net required')

def reserved_ids(c,project):
    used=set()
    for row in c.execute("SELECT body FROM revisions WHERE project=? AND module='blanket'",(project,)):
        for entry in json.loads(row['body'])['document_edits']:
            if entry.get('kind')!='blanket_net_v1':continue
            used.update(entry['point_state']['used_ids'])
            command=entry.get('point_command') or {}
            if command.get('action')=='add':used.add(command['id'])
            if command.get('action')=='spacing':used.update(command['ids'])
    return used

def prepare_net(repo,c,p,revision,operation,request,payload,cover):
    require(not cover.get('manufacturing_summary',{}).get('requirements_unmet'),422,'piece_limit_exceeded','Final cutting pieces per layer exceed configured hard limit')
    params=request['parameters'];source=current_net(repo,c,p['id'],revision['id'],params['result_id'],optional=operation=='blanket.unfold')
    if operation!='blanket.unfold':require(source is not None,409,'result_conflict')
    # An existing edit history must retain its effective state. Resolve the
    # current revision's net even when unfold was submitted using a cover run;
    # do not replace documented deletions with a fresh empty state. Geometry
    # and replay remain in the worker, never in this HTTP preparation path.
    if source is None and revision['document_edits']:
        source=current_net(repo,c,p['id'],revision['id'])
    settings=copy.deepcopy(source['net']['settings']) if source else {}
    point_state=copy.deepcopy(source['net']['point_state']) if source else dict(points=[],used_ids=[])
    point_state['used_ids']=sorted(set(point_state['used_ids'])|{id_ for id_ in reserved_ids(c,p['id']) if not (id_.startswith('fp:auto:') and id_.endswith(':initialized'))})
    command=None
    if operation=='blanket.unfold':
        settings=copy.deepcopy(params.get('settings',{}))
        if settings.pop('separate_panels',False):
            from .seams import adjacency
            _,pairs=adjacency(cover['panels'])
            settings.update(fold_seam_ids=[],cut_seam_ids=[s['id'] for s in pairs])
    elif operation=='blanket.edit_seams':
        edits={e['id']:e for e in settings.get('seam_overrides',[])}
        edits.update({e['id']:e for e in params['seams']});settings['seam_overrides']=list(edits.values())
    else:
        command=copy.deepcopy(params['command'])
        if command['action']=='add':
            command.setdefault('id','fp:'+str(uuid.uuid4()))
            require(command['id'] not in point_state['used_ids'],422,'point_id_already_used')
        elif command['action']=='spacing':
            quotient=math.dist(command['start_uv_mm'],command['end_uv_mm'])/command['spacing_mm']
            require(math.isfinite(quotient) and quotient<10000,422,'point_budget')
            n=math.floor(quotient)+1
            require(n<=10000 and n+len(point_state['points'])<=10000,422,'point_budget')
            command['ids']=['fp:'+str(uuid.uuid4()) for _ in range(n)]
    data=copy.deepcopy(revision)
    annotations=copy.deepcopy(revision['document_edits'][0].get('annotations',{})) if revision['document_edits'] else {}
    data['document_edits']=[dict(kind='blanket_net_v1',settings=settings,point_state=point_state,point_command=command,annotations=annotations)]
    payload['target_revision']=repo.make_revision(c,p['id'],'blanket',revision['id'],revision['model_ref'],data)
    payload['baseline']=cover['baseline']

def rebuild_net(cover,revision,output):
    from .net_pipeline import generate_net
    entries=revision['document_edits']
    if not entries:
        if cover['parameters'].get('envelope_policy')=='feature_composite_v1':return generate_net(cover,output=output)
        return None
    if len(entries)!=1 or entries[0].get('kind')!='blanket_net_v1':raise ValueError('invalid net editing state')
    state=entries[0]
    net=generate_net(cover,state['settings'],state['point_state'],state['point_command'],output)
    annotations=state.get('annotations',{})
    if annotations:
        from ..paint.commands import validate_command
        from ..drawing.document import DrawingDocument
        from ..domain.validation import canonical
        doc=net['drawing_document']
        doc['layers'].append(dict(name='TEXT',color=7,line_type='CONTINUOUS'))
        for key,a in annotations.items():
            validate_command('drawing.edit_annotation',dict(a,result_id='replay'))
            if a['annotation_id']!=key:raise ValueError('annotation identity mismatch')
            doc['entities'].append(dict(id=f"{revision['id']}:annotation:{key}",kind='text',layer='TEXT',source_refs=doc['source_links'],text=a['text'],position=a['position'],height_mm=2.5))
        DrawingDocument(doc);validate('blanket',net,'NetResult')
        if output is not None:
            (output/'blanket-net.json').write_text(canonical(net));(output/'drawing.json').write_text(canonical(doc))
    return net
