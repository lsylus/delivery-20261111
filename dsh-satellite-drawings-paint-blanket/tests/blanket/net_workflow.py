"""B11 real STEP -> HTTP -> isolated worker -> persistent net and engineering bundle."""
import copy,json,hashlib
from pathlib import Path
from jsonschema import Draft202012Validator
from referencing import Registry,Resource
from workflow import Service,setup,run,current,result

def current_net(s,p):return s.call('GET',f'/projects/{p}/blanket-net',who='blanket')[1]

def exercise(directory,archive=None):
    s=Service(directory);records=[]
    def save(name,value):
        if archive:(archive/f'{name}.json').write_text(json.dumps(value,indent=2)+'\n')
    def execute(p,operation,parameters):
        rev=current(s,p);r=run(s,p,rev,operation,parameters);records.append(r['id']);return r
    try:
        p,rev,asset,model=setup(s)
        execute(p,'blanket.generate',rev['parameters']);cover=result(s,p)
        assert current_net(s,p) is None
        first=execute(p,'blanket.unfold',dict(result_id=cover['result_id']))
        n=current_net(s,p);assert len(n['net']['pieces'])==1 and n['net']['areas']['overlap_mm2']==6300
        root=Path(__file__).resolve().parents[2]
        api=json.loads((root/'contracts/openapi.yaml').read_text())
        schema=copy.deepcopy(api['paths']['/projects/{id}/blanket-net']['get']['responses']['200']['content']['application/json']['schema'])
        schema['$id']='https://satellite-drawings.invalid/contracts/b11-response.schema.json'
        schemas=[json.loads(p.read_text()) for p in (root/'contracts').glob('*.schema.json')]
        registry=Registry().with_resources((s['$id'],Resource.from_contents(s)) for s in schemas)
        Draft202012Validator(schema,registry=registry).validate(n)
        s.operation(p,current(s,p),'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='spacing',panel_key='z+',start_uv_mm=[10,10],end_uv_mm=[90,10],spacing_mm=5e-324)),who='blanket',expected=422)
        assert current_net(s,p)==n
        save('cross',n)
        s.call('GET',f'/projects/{p}/blanket-net',who='alice',expected=403)
        s.call('GET','/artifacts/'+n['artifact']['id'],who='bob',expected=404)
        s.operation(p,rev,'blanket.unfold',dict(result_id=cover['result_id']),who='blanket',expected=409)
        # Idempotent point addition must not create another candidate or point ID.
        rev=current(s,p);params=dict(result_id=n['result_id'],command=dict(action='add',id='persistent-anchor',panel_key='z+',uv_mm=[50,50]))
        queued=s.operation(p,rev,'blanket.edit_fixed_points',params,who='blanket',key='add-once')
        assert s.operation(p,rev,'blanket.edit_fixed_points',params,who='blanket',key='add-once')==queued
        added=s.wait(queued['run_id'],'blanket');assert added['state']=='succeeded',added;records.append(added['id'])
        n=current_net(s,p);assert len(n['net']['fixed_points'])==1
        first_point=n['net']['fixed_points'][0];assert first_point['id']=='persistent-anchor'
        execute(p,'history.undo',{});earlier=current_net(s,p)
        assert not earlier['net']['fixed_points']
        s.operation(p,current(s,p),'blanket.edit_fixed_points',dict(result_id=earlier['result_id'],command=params['command']),who='blanket',expected=422)
        execute(p,'history.redo',{});n=current_net(s,p)
        rev=current(s,p)
        s.operation(p,rev,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=params['command']),who='blanket',expected=422)
        # Recuts and changed base rebind the same point at the same world location.
        cuts=[x['id'] for x in n['net']['seams']]
        execute(p,'blanket.unfold',dict(result_id=n['result_id'],settings=dict(base_panel='x+',fold_seam_ids=[],cut_seam_ids=cuts)))
        n=current_net(s,p);assert len(n['net']['pieces'])==5
        assert n['net']['fixed_points'][0]['position3d']==first_point['position3d'] and n['net']['fixed_points'][0]['mapping_ref']!=first_point['mapping_ref']
        # Seam ownership changes invoke the same worker, keeping the B10 volume.
        seam=n['net']['seams'][0]
        execute(p,'blanket.edit_seams',dict(result_id=n['result_id'],seams=[dict(id=seam['id'],kind='join',overlap_owner_panel='x+',width_mm=15)]))
        n=current_net(s,p);assert n['net']['cover_checks']==cover['blanket']['checks']
        # Point spacing creates persistent IDs and exact millimetre positions.
        execute(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='spacing',panel_key='z+',start_uv_mm=[10,10],end_uv_mm=[90,10],spacing_mm=20)))
        n=current_net(s,p);assert len(n['net']['fixed_points'])==6
        before_failure=current(s,p);old=n
        bad=s.wait(s.operation(p,before_failure,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='add',id='outside',panel_key='z+',uv_mm=[500,500])),who='blanket')['run_id'],'blanket')
        assert bad['state']=='failed' and not bad['artifacts'] and bad['checks'][0]['observed']['code']=='point_outside_material_or_in_hole'
        assert current(s,p)==before_failure and current_net(s,p)==old;save('rejected',bad)
        # Undo branches also retain the reservation of a deleted identity.
        execute(p,'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=dict(action='delete',id='persistent-anchor')))
        execute(p,'history.undo',{});n=current_net(s,p);assert any(x['id']=='persistent-anchor' for x in n['net']['fixed_points'])
        execute(p,'history.redo',{});n=current_net(s,p)
        s.operation(p,current(s,p),'blanket.edit_fixed_points',dict(result_id=n['result_id'],command=params['command']),who='blanket',expected=422)
        save('before-save',n)
        saved=execute(p,'engineering.save',{});bundle_a=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle')
        bundle=s.call('GET','/artifacts/'+bundle_a['id'],who='blanket')[1];assert bundle['rebuilder_version']=='b11-state-v1';save('bundle',bundle)
        ids=[x['id'] for x in n['net']['fixed_points']]
        s.stop();s.start()
        restored=execute(p,'engineering.restore',dict(artifact_id=bundle_a['id']));n=current_net(s,p)
        assert [x['id'] for x in n['net']['fixed_points']]==ids and n['net']['revision_id']!=old['net']['revision_id']
        assert n['net']['cover_checks']==cover['blanket']['checks'];save('restored',n)
        regenerated=execute(p,'blanket.generate',current(s,p)['parameters']);n=current_net(s,p)
        assert [x['id'] for x in n['net']['fixed_points']]==ids
        for label,r in [('cross',first),('restored',restored),('regenerated',regenerated)]:
            for a in r['artifacts']:
                data=s.call('GET','/artifacts/'+a['id'],who='blanket',raw=True)[1]
                assert hashlib.sha256(data).hexdigest()==a['sha256']
                if archive:
                    dest=archive/label/a['relative_storage_path'].split('/',2)[2];dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
        return dict(status='pass',runs=records,ports=s.ports,resources_created=[str(directory)],resources_cleaned=[str(directory)],point_ids=ids)
    finally:s.close()
