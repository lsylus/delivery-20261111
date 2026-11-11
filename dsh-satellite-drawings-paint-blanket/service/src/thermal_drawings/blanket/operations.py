"""Version-bound B10 orchestration, without importing OCP into HTTP."""
from thermal_drawings.domain.acceptance import usable
import copy
import json
from ..domain.errors import require
from ..domain.validation import validate
from ..storage.assets import controlled, sha


def current_result(repo,c,project,revision,result_id=None,optional=False):
    rows=c.execute("SELECT a.body,r.state FROM artifacts a JOIN runs r ON json_extract(a.body,'$.run_id')=r.id WHERE a.project=? AND a.module='blanket' ORDER BY a.rowid DESC",(project,)).fetchall()
    for row in rows:
        a=json.loads(row['body'])
        if row['state']!='succeeded' or a['role']!='blanket_result' or a['revision_id']!=revision or (result_id is not None and a['run_id']!=result_id):
            continue
        path=controlled(repo.root,a['relative_storage_path'])
        require(path.is_file() and sha(path)==a['sha256'],409,'integrity_failed')
        value=json.loads(path.read_text());validate('blanket',value,'BlanketResult')
        require(value['revision_id']==revision,409,'result_conflict')
        return dict(result_id=a['run_id'],blanket=value,artifact=a)
    if optional:
        return None
    require(False,409,'result_conflict','Exact current blanket result required')


def prepare(repo,c,p,principal,operation,request,payload):
    revision=payload['revision']
    if operation=='blanket.generate':
        params=request['parameters']
        require(params['model_ref']==revision['model_ref'],409,'unsaved_edits')
        if params!=revision['parameters']:
            data=copy.deepcopy(revision);data.update(parameters=copy.deepcopy(params),selection=params['included_faces']+params['excluded_faces'],document_edits=[])
            payload['target_revision']=repo.make_revision(c,p['id'],'blanket',revision['id'],revision['model_ref'],data)
        require(not revision['overrides'],422,'unsupported_overrides')
        require(all(r in params['included_faces']+params['excluded_faces'] for r in payload.get('target_revision',revision)['selection']),409,'selection_conflict')
        for ancestor in payload['history']:
            previous=current_result(repo,c,p['id'],ancestor['id'],optional=True)
            if previous:
                payload['baseline']=previous['blanket']['baseline']
                break
    elif operation in ('blanket.unfold','blanket.edit_seams','blanket.edit_fixed_points'):
        from .net_operations import prepare_net
        source=current_result(repo,c,p['id'],revision['id'],request['parameters']['result_id'])
        prepare_net(repo,c,p,revision,operation,request,payload,source['blanket'])
    elif operation=='blanket.edit_shape':
        params=request['parameters'];validate('blanket',params,'EditShape')
        source=current_result(repo,c,p['id'],revision['id'],params['result_id'])
        require(params['baseline_id']==source['blanket']['baseline']['id'],409,'baseline_conflict')
        data=copy.deepcopy(revision)
        data['document_edits']=[]  # Shape changes invalidate the old manufacturing net.
        for key in ('dimensions_mm','openings','allowance','surface_options','clearance_options'):
            if key in params:
                data['parameters'][key]=params[key]
        validate('blanket',data['parameters'])
        payload['target_revision']=repo.make_revision(c,p['id'],'blanket',revision['id'],revision['model_ref'],data)
        payload['baseline']=source['blanket']['baseline']
    elif operation in ('drawing.export','drawing.edit_annotation'):
        from .net_operations import current_net
        source=current_net(repo,c,p['id'],revision['id'],request['parameters']['result_id'])
        require(usable(source['net']),409,'result_conflict')
        if operation=='drawing.export':
            payload['drawing_result']=source['net']
        else:
            data=copy.deepcopy(revision)
            require(len(data['document_edits'])==1 and data['document_edits'][0].get('kind')=='blanket_net_v1',409,'result_conflict')
            annotations=data['document_edits'][0].setdefault('annotations',{})
            command=copy.deepcopy(request['parameters']);command.pop('result_id')
            annotations[command['annotation_id']]=command
            payload['target_revision']=repo.make_revision(c,p['id'],'blanket',revision['id'],revision['model_ref'],data)
            payload['baseline']=current_result(repo,c,p['id'],revision['id'])['blanket']['baseline']
    elif operation=='engineering.save':
        from .net_operations import current_net
        net=current_net(repo,c,p['id'],revision['id'],optional=True)
        payload['net']=net['net'] if net else None
        require(not revision['document_edits'] or net is not None,409,'result_conflict','Recompute current net before saving')
        source=current_result(repo,c,p['id'],revision['id'],optional=True)
        require(source is None or not source['blanket'].get('manufacturing_summary',{}).get('requirements_unmet'),422,'piece_limit_exceeded','An over-limit preview cannot be saved as a manufacturing engineering bundle')
        if revision['parameters'].get('rule_version')=='blanket-v1':
            require(source is not None,409,'result_conflict','Generate the current revision before saving its baseline')
        payload['blanket']=source['blanket'] if source else None
        payload['blanket_artifacts']=[] if source is None else [json.loads(row['body']) for row in c.execute("SELECT body FROM artifacts WHERE project=? AND module='blanket' AND json_extract(body,'$.run_id')=?",(p['id'],source['result_id'])).fetchall()]
