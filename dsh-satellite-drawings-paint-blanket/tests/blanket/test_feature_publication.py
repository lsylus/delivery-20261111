"""Real STEP/HTTP publication: over-limit patterns stay visible, never exportable."""
import copy
import json
import time
from workflow import ROOT, Service, current, result, run, setup
from thermal_drawings.runtime.publication import reviewable_limit_preview, reviewable_feature_net_preview


class FeatureService(Service):
    def wait(self,id_,who='alice'):
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            value=self.call('GET','/runs/'+id_,who=who)[1]
            if value['state'] in ('succeeded','failed','cancelled'):return value
            time.sleep(.3)
        raise AssertionError('Feature workflow exceeded 180 seconds')


def test_motor_limit_preview_publishes_native_net_and_rejects_manufacturing(tmp_path):
    service=FeatureService(tmp_path/'feature-preview',timeout=180,upload_limit=16*1024*1024)
    service.stop()
    converter=tmp_path/'disabled-converter.json'
    converter.write_text(json.dumps({'dwg':{'adapter':'must-not-be-invoked'}}))
    config=json.loads(service.config.read_text());config['converter_config']=str(converter)
    service.config.write_text(json.dumps(config));service.start()
    try:
        project=service.project('blanket')
        path=ROOT/'docs/evidence/B13/r4-review/run-01/complete-motor.step'
        asset=service.call('POST',f'/projects/{project}/assets',path.read_bytes(),who='blanket',expected=201,
                           headers={'Content-Type':'application/step','X-Filename':'motor.step'})[1]
        imported=service.wait(service.submit_import(project,asset,who='blanket'),'blanket')
        assert imported['state']=='succeeded',imported
        rev=current(service,project)
        model=service.call('GET',f"/projects/{project}/models/{rev['model_ref']['model_id']}",who='blanket')[1]
        artifact=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'))
        mapping=service.call('GET','/artifacts/'+artifact['id'],who='blanket')[1]
        refs=[f['face_ref'] for f in mapping['faces']]
        plane=min((r for r in refs if r['signature']['type']=='PLANE'),key=lambda r:r['signature']['centroid_mm'][2])
        params=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text())
        params.update(model_ref=rev['model_ref'],target_instances=sorted({r['instance_id'] for r in refs}),
                      installation_face=plane,envelope_policy='feature_composite_v1',piece_limit=10)
        params['installation_frame']['origin']=plane['signature']['centroid_mm']
        finished=run(service,project,rev,'blanket.generate',params)
        assert next(c for c in finished['checks'] if c['id']=='publication')['observed']['preview_only'] is True
        cover=result(service,project)['blanket']
        published=service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]
        net=published['net']
        assert cover['feature_composite']['primitive_count']==8
        assert len(net['pieces'])>10 and net['manufacturing_summary']['pieces_per_layer']==len(net['pieces'])
        assert net['status']=='failed' and not net['diagnostics']
        assert net['fixed_points'] and net['drawing_document']['entities']
        assert reviewable_feature_net_preview(net,cover)
        # No other geometric/topological failure may be hidden as a cap preview.
        broken=copy.deepcopy(net);broken['diagnostics']=[{'code':'bad_material'}]
        assert not reviewable_feature_net_preview(broken,cover)
        broken=copy.deepcopy(net);next(c for c in broken['checks'] if c['id']=='net_topology_material')['status']='fail'
        assert not reviewable_feature_net_preview(broken,cover)
        broken=copy.deepcopy(cover);next(c for c in broken['checks'] if c['id']=='coverage')['status']='fail'
        assert not reviewable_limit_preview(broken)
        rev=current(service,project)
        rejected=service.operation(project,rev,'drawing.export',dict(result_id=published['result_id'],draft=True),who='blanket',expected=409)
        assert rejected['code']=='result_conflict'
        rejected=service.operation(project,rev,'engineering.save',{},who='blanket',expected=422)
        assert rejected['code']=='piece_limit_exceeded'
        rejected=service.operation(project,rev,'blanket.edit_fixed_points',dict(result_id=published['result_id'],
                                   command=dict(action='delete',id=net['fixed_points'][0]['id'])),who='blanket',expected=422)
        assert rejected['code']=='piece_limit_exceeded'
        assert current(service,project)==rev
        # Explicitly raising the user constraint publishes the same complete
        # geometry as an editable draft; it does not drop or disguise patterns.
        params['piece_limit']=50
        run(service,project,rev,'blanket.generate',params)
        usable=service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]
        assert usable['net']['status']=='needs_review'
        assert len(usable['net']['pieces'])==len(net['pieces'])
        assert usable['net']['manufacturing_summary']['requirements_unmet']==[]
        assert [p['id'] for p in usable['net']['fixed_points']]==[p['id'] for p in net['fixed_points']]
    finally:
        service.close()


def test_deleted_automatic_markers_stay_deleted_across_unfold_restore_and_undo(tmp_path):
    service=FeatureService(tmp_path/'marker-history',timeout=180)
    try:
        project,rev,_,model=setup(service)
        artifact=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'))
        mapping=service.call('GET','/artifacts/'+artifact['id'],who='blanket')[1]
        plane=min((f['face_ref'] for f in mapping['faces'] if f['face_ref']['signature']['type']=='PLANE'),
                  key=lambda r:r['signature']['centroid_mm'][2])
        params=copy.deepcopy(rev['parameters'])
        params.update(envelope_policy='feature_composite_v1',installation_face=plane,piece_limit=10)
        params['installation_frame']['origin']=plane['signature']['centroid_mm']
        run(service,project,rev,'blanket.generate',params)

        def net():return service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1]
        def execute(op,values=None):return run(service,project,current(service,project),op,values)

        first=net();ids=[p['id'] for p in first['net']['fixed_points']]
        assert ids
        for point_id in ids:
            execute('blanket.edit_fixed_points',dict(result_id=net()['result_id'],command=dict(action='delete',id=point_id)))
        assert net()['net']['fixed_points']==[]
        execute('history.undo')
        assert [p['id'] for p in net()['net']['fixed_points']]==ids[-1:]
        execute('history.redo')
        assert net()['net']['fixed_points']==[]
        execute('blanket.unfold',dict(result_id=net()['result_id'],settings={}))
        assert net()['net']['fixed_points']==[]
        saved=execute('engineering.save')
        bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle')
        service.stop();service.start()
        execute('engineering.restore',dict(artifact_id=bundle['id']))
        assert net()['net']['fixed_points']==[]
        execute('blanket.generate',current(service,project)['parameters'])
        assert net()['net']['fixed_points']==[]
        assert set(ids)<=set(net()['net']['point_state']['used_ids'])
    finally:
        service.close()
