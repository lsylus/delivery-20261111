"""Actual HTTP boundaries for nonmutating frame previews and stale inputs."""
import copy,json,sys
from pathlib import Path
import cadquery as cq
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from b13_workflow import Service,import_shape,current,run,result

def test_installation_preview_native_validation_and_revision_boundaries(tmp_path):
    service=Service(tmp_path/'installation-http',timeout=120)
    try:
        service.stop();cfg=json.loads(service.config.read_text());cfg['converter_config']=str(ROOT/'work/config/converters.local.json');service.config.write_text(json.dumps(cfg));service.start()
        project=service.project('blanket')
        rev,model,mapping=import_shape(service,project,cq.Solid.makeBox(25.4,50.8,76.2))
        refs=[row['face_ref'] for row in mapping['faces']]
        ref=min((r for r in refs if r['signature']['type']=='PLANE'),key=lambda r:r['signature']['centroid_mm'][2])
        options=dict(x_direction=[1,0,0],rotation_deg=0,origin_mode='bounds_min',offset_mm=[0,0])
        params=dict(face_ref=ref,installation_setup=options,deflection_mm=.5,cuts_u=[])
        measured=run(service,project,rev,'geometry.analyze',params)
        artifact=next(a for a in measured['artifacts'] if a['role']=='complex_analysis')
        report=service.call('GET','/artifacts/'+artifact['id'],who='blanket')[1]
        assert report['result']['source_face_count']==6 and report['manufacturing_approved'] is False
        assert abs(report['result']['local_bounds_mm'][1][0]-25.4)<1e-5
        assert current(service,project)['id']==rev['id'] and result(service,project) is None
        for vector in ([0,0,0],[0,0,1]):
            invalid=copy.deepcopy(params);invalid['installation_setup']['x_direction']=vector
            failed=service.wait(service.operation(project,rev,'geometry.analyze',invalid,who='blanket')['run_id'],'blanket')
            assert failed['state']=='failed'
            assert current(service,project)['id']==rev['id']
        invalid=copy.deepcopy(params);invalid['installation_setup']['offset_mm']=[1000001,0]
        service.operation(project,rev,'geometry.analyze',invalid,who='blanket',expected=422)
        stale=copy.deepcopy(params);stale['face_ref']['model_revision']+=1
        service.operation(project,rev,'geometry.analyze',stale,who='blanket',expected=409)
        cover=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text())
        cover.update(model_ref=rev['model_ref'],target_instances=[ref['instance_id']],installation_face=ref,
                     installation_frame=report['result']['frame'],installation_setup=options,
                     envelope_policy='faceted_clearance_v1',clearance_options=dict(clearance_mm=.1,section_cuts_mm=[]))
        cover['allowance']['factors']=[1,1,1]
        tampered=copy.deepcopy(cover);tampered['installation_frame']['origin'][0]+=5
        failed=service.wait(service.operation(project,rev,'blanket.generate',tampered,who='blanket')['run_id'],'blanket')
        assert failed['state']=='failed' or any(c['status']=='fail' for c in failed['checks'])
        assert result(service,project) is None
        # Failed candidates may create a revision; always use its actual current head.
        rev=current(service,project)
        generated=run(service,project,rev,'blanket.generate',cover);actual=result(service,project)
        assert actual['blanket']['status']=='needs_review'
        before=current(service,project)
        new,_,_=import_shape(service,project,cq.Solid.makeBox(30,60,90),expected=before['id'],name='replacement.step')
        assert new['model_ref']!=before['model_ref']
        service.operation(project,before,'geometry.analyze',params,who='blanket',expected=409)
        service.operation(project,new,'geometry.analyze',params,who='blanket',expected=409)
        service.operation(project,new,'drawing.export',dict(result_id=actual['result_id'],draft=True),who='blanket',expected=409)
        assert result(service,project) is None
    finally:service.close()
