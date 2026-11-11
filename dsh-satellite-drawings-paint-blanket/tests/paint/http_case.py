"""Actual HTTP/worker acceptance; credentials remain inside a temporary fixture."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
from b08_cases import override

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('b08_http_harness',ROOT/'tests/runtime/http_harness.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
Service=module.Service


def imported_case(service):
    project=service.project()
    data=(ROOT/'fixtures/synthetic/paint/assembly.step').read_bytes()
    asset=service.call('POST',f'/projects/{project}/assets',data,expected=201,
                       headers={'Content-Type':'application/step','X-Filename':'paint.step'})[1]
    run=service.wait(service.submit_import(project,asset))
    assert run['state']=='succeeded',run
    head=service.call('GET',f'/projects/{project}')[1]['module_states']['paint']
    revision=service.call('GET',f'/projects/{project}/revisions/{head}')[1]
    a=next(a for a in run['artifacts'] if a['relative_storage_path'].endswith('/mesh-map.json'))
    refs=[e['face_ref'] for e in json.loads(service.call('GET',a['download_url'].removeprefix('/api/v1'),raw=True)[1])['faces']]
    top=max((r for r in refs if r['signature']['normal'] and r['signature']['normal'][2]>.9),key=lambda r:r['signature']['area_mm2'])
    rib=next(r for r in refs if r['signature']['type']=='PLANE' and abs(r['signature']['area_mm2']-50)<1e-6 and abs(r['signature']['centroid_mm'][2]-6)<1e-6)
    params=dict(schema_version=1,model_ref=revision['model_ref'],target_face_refs=[top],scope_boundary=None,
                contact_threshold_mm=.1,contact_comparison='lt',contact_offset_mm=3,hole_offset_mm=3,
                boss_rule='protect',boss_additional_offset_mm=0,rib_rule='retain_paint',overrides=[override(rib,'rib')],rule_version='paint-v1')
    revision=service.call('POST',f'/projects/{project}/revisions',dict(expected_revision=head,model_ref=revision['model_ref'],
        parameters=params,selection=[top],overrides=params['overrides']),expected=201)[1]
    return project,revision,run,refs


def download(service,run):
    result={}
    for a in run['artifacts']:
        data=service.call('GET',a['download_url'].removeprefix('/api/v1'),raw=True)[1]
        assert hashlib.sha256(data).hexdigest()==a['sha256'] and len(data)==a['bytes']
        result[a['relative_storage_path'].rsplit('/',1)[1]]=data
    return result


def exercise(service):
    p,rev,imported,refs=imported_case(service)
    key='b08-generate'
    id_=service.operation(p,rev,'paint.generate',rev['parameters'],key=key)['run_id']
    run=service.wait(id_)
    assert run['state']=='succeeded', (run,[x.read_text() for x in (service.data/'jobs').glob('*.log')])
    files=download(service,run);paint=json.loads(files['paint-result.json'])
    assert paint['status']=='passed' and len(paint['regions'])==4,paint['diagnostics']
    assert paint['drawing_document']==json.loads(files['drawing.json'])
    assert paint['revision_id']==rev['id'] and all(c['status']=='pass' for c in run['checks'])
    assert service.operation(p,rev,'paint.generate',rev['parameters'],key=key)['run_id']==id_
    changed=copy.deepcopy(rev['parameters']);changed['contact_offset_mm']=4
    service.operation(p,rev,'paint.generate',changed,expected=409)
    duplicate=copy.deepcopy(rev['parameters'])
    unused=override(rev['selection'][0],'exclude')
    unused['id']=duplicate['overrides'][0]['id']
    duplicate['overrides'].append(unused)
    service.operation(p,rev,'paint.generate',duplicate,expected=422)
    for a in run['artifacts']:
        service.call('GET',a['download_url'].removeprefix('/api/v1'),who='bob',expected=404)
    # Unknown classification is a draft, cannot replace the current passed result.
    unknown=copy.deepcopy(rev['parameters']);unknown['overrides'][0]['classification']='unknown'
    draft_rev=service.call('POST',f'/projects/{p}/revisions',dict(expected_revision=rev['id'],model_ref=rev['model_ref'],
          parameters=unknown,selection=rev['selection'],overrides=unknown['overrides']),expected=201)[1]
    draft=service.wait(service.operation(p,draft_rev,'paint.generate',unknown)['run_id'])
    assert draft['state']=='succeeded' and any(c['status']=='needs_review' for c in draft['checks'])
    assert draft['checks'][0]['observed']['current'] is False
    assert json.loads(download(service,draft)['paint-result.json'])['status']=='needs_review'
    # A malformed scope fails in the worker, persists diagnostics and publishes no artifacts.
    broken=copy.deepcopy(unknown);broken['scope_boundary']=dict(points=[[0,0],[5,5],[5,0],[0,5]],closed=True,orientation='ccw')
    bad_rev=service.edit(p,draft_rev,broken)
    bad=service.wait(service.operation(p,bad_rev,'paint.generate',broken)['run_id'])
    assert bad['state']=='failed' and bad['artifacts']==[] and bad['error']['code']=='paint_failed'
    assert any(c['reason']=='invalid_scope' for c in bad['checks'])
    assert service.call('GET','/runs/'+run['id'])[1]==run
    assert download(service,run)==files
    # Same source and rules survive the existing engineering save/restore path.
    saved=service.wait(service.operation(p,bad_rev)['run_id'])
    assert saved['state']=='succeeded'
    service.stop();service.start()
    assert download(service,run)==files
    restored=service.wait(service.operation(p,bad_rev,'engineering.restore',{'artifact_id':saved['artifacts'][0]['id']})['run_id'])
    assert restored['state']=='succeeded'
    return dict(status='pass',run=run,draft_run=draft,failed_run=bad,save_run=saved,restore_run=restored,
                ports=service.ports,source_sha256=hashlib.sha256((ROOT/'fixtures/synthetic/paint/assembly.step').read_bytes()).hexdigest()),files
