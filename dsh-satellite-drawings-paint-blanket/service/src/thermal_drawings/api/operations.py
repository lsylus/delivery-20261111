"""B09 transactional orchestration. No native computation runs in HTTP."""
import copy
import json
from ..domain.errors import require
from ..domain.validation import canonical
from ..storage.assets import controlled, sha
from ..paint.commands import prepare_edit

PAINT_OPERATIONS = ('paint.generate', 'paint.edit_regions', 'drawing.edit_annotation')


def paint_result(repo, c, project, module, revision, result_id=None, optional=False):
    rows = c.execute('SELECT a.body,r.state FROM artifacts a JOIN runs r ON json_extract(a.body,\'$.run_id\')=r.id WHERE a.project=? AND a.module=? ORDER BY a.rowid DESC', (project, module)).fetchall()
    for row in rows:
        a=json.loads(row['body'])
        if row['state'] != 'succeeded' or a['role'] != 'paint_result' or a['revision_id'] != revision:
            continue
        if result_id is not None and a['run_id'] != result_id:
            continue
        path=controlled(repo.root,a['relative_storage_path'])
        require(path.is_file() and sha(path)==a['sha256'],409,'integrity_failed')
        paint=json.loads(path.read_text())
        require(paint['revision_id']==revision,409,'result_unavailable')
        if paint['drawing_document'] is None:
            if optional:
                return dict(result_id=a['run_id'],paint=paint,artifact=a)
            require(False,409,'result_unavailable','This result has diagnostics but no editable drawing')
        return dict(result_id=a['run_id'],paint=paint,artifact=a)
    if optional:
        return None
    require(False,409,'result_conflict','Select a result from the exact current engineering revision')


def _paint_artifact(repo, c, project, module, revision, role, result_id=None, optional=False):
    rows = c.execute('SELECT a.body,r.state FROM artifacts a JOIN runs r ON json_extract(a.body,\'$.run_id\')=r.id WHERE a.project=? AND a.module=? ORDER BY a.rowid DESC', (project, module)).fetchall()
    for row in rows:
        artifact = json.loads(row['body'])
        if row['state'] != 'succeeded' or artifact['role'] != role or artifact['revision_id'] != revision:
            continue
        if result_id is not None and artifact['run_id'] != result_id:
            continue
        path = controlled(repo.root, artifact['relative_storage_path'])
        require(path.is_file() and sha(path) == artifact['sha256'], 409, 'integrity_failed')
        value = json.loads(path.read_text())
        require(value['revision_id'] == revision, 409, 'result_unavailable')
        return dict(result_id=artifact['run_id'], artifact=artifact, value=value)
    if optional:
        return None
    require(False, 409, 'result_conflict', 'Select a result from the exact current engineering revision')


def paint_recommendations(repo, c, project, module, revision, optional=False):
    if revision == 'empty':
        if optional:
            return None
        require(False, 409, 'result_conflict', 'Generate recommendations for the current model')
    current = repo.revision(c, project, module, revision)
    rows = c.execute(
        'SELECT a.body,r.state FROM artifacts a JOIN runs r ON json_extract(a.body,\'$.run_id\')=r.id '
        'WHERE a.project=? AND a.module=? ORDER BY a.rowid DESC', (project, module)
    ).fetchall()
    for row in rows:
        artifact = json.loads(row['body'])
        if row['state'] != 'succeeded' or artifact['role'] != 'paint_recommendations':
            continue
        source_revision = repo.revision(c, project, module, artifact['revision_id'])
        if source_revision['model_ref'] != current['model_ref']:
            continue
        path = controlled(repo.root, artifact['relative_storage_path'])
        require(path.is_file() and sha(path) == artifact['sha256'], 409, 'integrity_failed')
        value = json.loads(path.read_text())
        require(value['revision_id'] == artifact['revision_id'] and value['model_ref'] == current['model_ref'],
                409, 'result_unavailable')
        return dict(result_id=artifact['run_id'], recommendations=value, artifact=artifact)
    if optional:
        return None
    require(False, 409, 'result_conflict', 'Generate recommendations for the current model')


def paint_batch_result(repo, c, project, module, revision, result_id=None, optional=False):
    source = _paint_artifact(repo, c, project, module, revision, 'paint_batch_result', result_id, optional)
    return None if source is None else dict(result_id=source['result_id'], batch=source['value'], artifact=source['artifact'])


def prepare(repo,c,p,principal,operation,request,payload):
    revision=payload['revision']
    if operation=='engineering.rebind':
        from ..domain.revision_transfer import prepare as prepare_transfer
        prepare_transfer(repo,c,p,principal,request,payload)
        return
    if operation=='geometry.analyze':
        from ..domain.complex_analysis import prepare as prepare_analysis
        prepare_analysis(repo,c,p,principal,request,payload)
        return
    if principal.module == 'blanket':
        from ..blanket.operations import prepare as prepare_blanket
        prepare_blanket(repo,c,p,principal,operation,request,payload)
    if principal.module == 'paint' and operation in ('paint.edit_regions','drawing.edit_annotation'):
        source=paint_result(repo,c,p['id'],principal.module,revision['id'],request['parameters']['result_id'])
        payload['paint']=source['paint']
        if operation != 'drawing.export':
            data=copy.deepcopy(revision)
            data['document_edits'].append(prepare_edit(operation,request['parameters'],source['paint'],revision))
            payload['target_revision']=repo.make_revision(c,p['id'],principal.module,revision['id'],revision['model_ref'],data)
    if principal.module == 'paint' and operation == 'drawing.export':
        if 'batch_result_id' in request['parameters']:
            source = paint_batch_result(repo,c,p['id'],principal.module,revision['id'],request['parameters']['batch_result_id'])
            payload['paint_batch'] = source['batch']
        else:
            source=paint_result(repo,c,p['id'],principal.module,revision['id'],request['parameters']['result_id'])
            payload['paint']=source['paint']
    if operation == 'engineering.save':
        source=paint_result(repo,c,p['id'],principal.module,revision['id'],optional=True)
        payload['paint']=source['paint'] if source else None
    if operation == 'engineering.restore':
        from ..storage.repository import uid
        payload['restored_id']=uid()


def history(repo,c,p,principal,operation,revision,run):
    row=c.execute('SELECT body FROM redo WHERE project=? AND module=?',(p['id'],principal.module)).fetchone()
    stack=json.loads(row['body']) if row else []
    if operation == 'history.undo':
        require(revision['parent_id'] is not None,409,'history_empty','No earlier engineering revision')
        target=repo.revision(c,p['id'],principal.module,revision['parent_id'])
        stack.append(revision['id'])
    else:
        require(bool(stack),409,'history_empty','No redo branch')
        target=repo.revision(c,p['id'],principal.module,stack.pop())
        require(target['parent_id']==revision['id'],409,'history_conflict')
    repo.move_head(c,p,principal.module,target,clear_redo=False)
    c.execute('INSERT OR REPLACE INTO redo VALUES(?,?,?)',(p['id'],principal.module,canonical(stack)))
    run.update(state='succeeded',progress=1,checks=[dict(id='history',status='pass',scope_refs=[],observed={'revision_id':target['id']},limit=None,units=None,algorithm_version='b09-history-v1',evidence_refs=[],reason='Persisted engineering head changed')])
    repo.put_run(c,run)
