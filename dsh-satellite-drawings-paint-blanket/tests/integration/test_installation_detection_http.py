import json
import sys

import cadquery as cq

from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from workflow import Service,current


def test_detection_operation_publishes_unique_aggregated_contact_without_revision_change(tmp_path):
    source=tmp_path/'installation.step'
    assembly=cq.Assembly(name='satellite')
    assembly.add(cq.Solid.makeBox(10,10,10),name='target')
    assembly.add(cq.Solid.makeBox(5,10,2,cq.Vector(0,0,-2.05)),name='support-left')
    assembly.add(cq.Solid.makeBox(5,10,2,cq.Vector(5,0,-2.05)),name='support-right')
    assembly.export(str(source),'STEP')
    service=Service(tmp_path/'service',timeout=120,upload_limit=2*1024*1024)
    try:
        project=service.project('blanket')
        asset=service.call('POST',f'/projects/{project}/assets',source.read_bytes(),who='blanket',expected=201,
                           headers={'Content-Type':'application/step','X-Filename':'installation.step'})[1]
        imported=service.wait(service.submit_import(project,asset,who='blanket'),'blanket')
        assert imported['state']=='succeeded',imported
        revision=current(service,project)
        model=service.call('GET',f"/projects/{project}/models/{revision['model_ref']['model_id']}",who='blanket')[1]
        face_map=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'))
        mapping=service.call('GET','/artifacts/'+face_map['id'],who='blanket')[1]
        physical={entry['face_ref']['instance_id'] for entry in mapping['faces']}
        names={row['name']:row['instance_id'] for row in model['snapshot']['instances'] if row['instance_id'] in physical}
        target=names['target']
        parameters=dict(target_instances=[target],excluded_instances=[],maximum_gap_mm=.1)
        finished=service.wait(service.operation(project,revision,'blanket.detect_installation',parameters,who='blanket')['run_id'],'blanket')
        assert finished['state']=='succeeded',(finished,[path.read_text()[-5000:] for path in (service.data/'jobs').glob('*.log')])
        artifact=next(a for a in finished['artifacts'] if a['role']=='installation_detection')
        detection=json.loads(service.call('GET','/artifacts/'+artifact['id'],who='blanket',raw=True)[1])
        assert detection['status']=='unique' and detection['maximum_gap_mm']==.1
        assert detection['revision_id']==revision['id'] and detection['model_ref']==revision['model_ref']
        assert len(detection['candidates'])==1
        candidate=detection['candidates'][0]
        assert candidate['target_face_ref']['instance_id']==target
        assert {ref['instance_id'] for ref in candidate['support_face_refs']}=={names['support-left'],names['support-right']}
        assert abs(candidate['gap_mm']-.05)<1e-7 and abs(candidate['contact_area_mm2']-100)<1e-6
        assert current(service,project)==revision
    finally:
        service.close()
