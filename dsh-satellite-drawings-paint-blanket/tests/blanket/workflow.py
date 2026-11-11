"""Real HTTP/STEP/worker/SQLite exercise, also used to archive native artifacts."""
import hashlib
import json
from pathlib import Path
import sys
import cadquery as cq
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/runtime'))
from http_harness import Service


def current(service,project):
    head=service.call('GET',f'/projects/{project}',who='blanket')[1]['module_states']['blanket']
    return service.call('GET',f'/projects/{project}/revisions/{head}',who='blanket')[1]


def result(service,project):
    return service.call('GET',f'/projects/{project}/blanket-result',who='blanket')[1]


def run(service,project,revision,operation,parameters=None):
    try:
        r=service.wait(service.operation(project,revision,operation,parameters,who='blanket')['run_id'],'blanket')
    except AssertionError as error:
        raise AssertionError([p.read_text()[-5000:] for p in (service.data/'jobs').glob('*.log')]) from error
    if r['state']!='succeeded':
        logs=[p.read_text()[-5000:] for p in (service.data/'jobs').glob('*.log')]
        raise AssertionError((r,logs))
    return r


def setup(service):
    p=service.project('blanket')
    path=ROOT/'fixtures/synthetic/blanket/box-100.step'
    asset=service.call('POST',f'/projects/{p}/assets',path.read_bytes(),who='blanket',expected=201,headers={'Content-Type':'application/step','X-Filename':'box.step'})[1]
    r=service.wait(service.submit_import(p,asset,who='blanket'),'blanket');assert r['state']=='succeeded',r
    rev=current(service,p);model=service.call('GET',f'/projects/{p}/models/'+rev['model_ref']['model_id'],who='blanket')[1]
    params=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text());params['model_ref']=rev['model_ref']
    params['target_instances']=[i['instance_id'] for i in model['snapshot']['instances'] if i['definition_id'] is not None and i.get('children',[])==[]]
    # ModelSnapshot may include aggregates; use the actual B02 face map leaves.
    amap=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'))
    mapping=service.call('GET','/artifacts/'+amap['id'],who='blanket')[1]
    params['target_instances']=sorted({f['face_ref']['instance_id'] for f in mapping['faces']})
    rev=service.edit(p,rev,params,who='blanket')
    return p,rev,asset,model


def exercise(directory,archive=None):
    s=Service(directory);records=[]
    try:
        p,rev,asset,model=setup(s)
        source_bytes=s.call('GET',f'/projects/{p}/assets/'+asset['id'],who='blanket',raw=True)[1]
        first_run=run(s,p,rev,'blanket.generate',rev['parameters']);first=result(s,p)
        assert first['blanket']['dimensions_mm']==[105,105,105]
        baseline=first['blanket']['baseline']
        for a in first_run['artifacts']:
            data=s.call('GET','/artifacts/'+a['id'],who='blanket',raw=True)[1]
            assert hashlib.sha256(data).hexdigest()==a['sha256']
            if archive:
                dest=archive/'generated'/a['relative_storage_path'].split('/',2)[2];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        # Rejection must preserve the exact old head and usable result.
        bad=s.wait(s.operation(p,rev,'blanket.edit_shape',dict(result_id=first['result_id'],baseline_id=baseline['id'],dimensions_mm=[95,110,110]),who='blanket')['run_id'],'blanket')
        assert bad['state']=='failed' and not bad['artifacts']
        assert next(c for c in bad['checks'] if c['id']=='volume_ratio')['status']=='pass'
        assert next(c for c in bad['checks'] if c['id']=='penetration')['status']=='fail'
        assert current(s,p)['id']==rev['id'] and result(s,p)['result_id']==first['result_id']
        params=dict(result_id=first['result_id'],baseline_id=baseline['id'],dimensions_mm=[100,110,100],openings=[dict(id='port',panel='z+',loop=dict(points=[[20,20],[30,20],[30,30],[20,30]],closed=True,orientation='ccw'))])
        edited_run=run(s,p,rev,'blanket.edit_shape',params);edited=current(s,p);edited_result=result(s,p)
        assert edited['id']!=rev['id'] and edited_result['blanket']['baseline']==baseline
        assert edited_result['blanket']['dimensions_mm']==[100,110,100]
        s.operation(p,rev,'blanket.edit_shape',params,who='blanket',expected=409)
        s.operation(p,edited,'blanket.edit_shape',dict(params,result_id=first['result_id']),who='blanket',expected=409)
        s.call('GET',f'/projects/{p}/blanket-result',who='alice',expected=403)
        s.call('GET','/artifacts/'+edited_run['artifacts'][0]['id'],who='bob',expected=404)
        saved=run(s,p,edited,'engineering.save');bundle_a=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle')
        bundle=s.call('GET','/artifacts/'+bundle_a['id'],who='blanket')[1]
        assert bundle['rebuilder_version']=='b10-state-v1' and bundle['construction_parameters']['blanket_result']['baseline']==baseline
        s.stop();s.start()
        assert current(s,p)['id']==edited['id']
        changed=run(s,p,edited,'blanket.edit_shape',dict(result_id=edited_result['result_id'],baseline_id=baseline['id'],dimensions_mm=[110,100,100]))
        revision=current(s,p)
        restored=run(s,p,revision,'engineering.restore',dict(artifact_id=bundle_a['id']))
        after=current(s,p);restored_result=result(s,p)
        assert after['id']!=edited['id'] and after['parameters']==edited['parameters']
        assert restored_result['blanket']['baseline']==baseline
        assert restored_result['blanket']['checks']==edited_result['blanket']['checks']
        # Recompute from the persisted revision, not a saved display mesh.
        recomputed=run(s,p,after,'blanket.generate',after['parameters'])
        assert result(s,p)['blanket']['baseline']==baseline
        assert s.call('GET',f'/projects/{p}/assets/'+asset['id'],who='blanket',raw=True)[1]==source_bytes
        assert s.call('GET',f'/projects/{p}/models/'+rev['model_ref']['model_id'],who='blanket')[1]==model
        for name,value in [('first',first),('rejected',bad),('edited',edited_result),('bundle',bundle),('restored',restored_result)]:
            if archive:
                (archive/f'{name}.json').write_text(json.dumps(value,indent=2)+'\n')
        for a in restored['artifacts']:
            data=s.call('GET','/artifacts/'+a['id'],who='blanket',raw=True)[1]
            assert hashlib.sha256(data).hexdigest()==a['sha256']
            if archive:
                dest=archive/'restored'/a['relative_storage_path'].split('/',2)[2];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        records=[first_run['id'],bad['id'],edited_run['id'],saved['id'],changed['id'],restored['id'],recomputed['id']]
        return dict(status='pass',runs=records,source_sha256=asset['sha256'],baseline_id=baseline['id'],ports=s.ports,
                    resources_created=[str(directory)],resources_cleaned=[str(directory)])
    finally:
        s.close()
