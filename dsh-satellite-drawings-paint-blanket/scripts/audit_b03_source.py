"""Read-only S behavior and provenance audit; does not load legacy callers."""
import ast, hashlib, importlib, json, subprocess, sys
from pathlib import Path
from unittest.mock import Mock, patch
from b03_cases import CAD, SOURCE, box, external_inputs, rectangle

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/B03'

def record(path):
    data=path.read_bytes()
    return dict(path=str(path),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))

def audit():
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(CAD))
    m=importlib.import_module('backend.geometry.solid_pairs')
    files=['backend/geometry/solid_pairs.py','backend/geometry/bounds.py','backend/satellite_geometry/modeling.py','backend/satellite_geometry/geometry.py','backend/tests/test_solid_pair_measurements.py','backend/tests/test_solid_pair_characterization.py','backend/tests/test_contact_patch_contract.py','backend/tests/test_contact_patch_characterization.py']
    sources=[]
    for rel in files:
        p=CAD/rel;tree=ast.parse(p.read_text())
        sources.append({**record(p),'relative_path':str(p.relative_to(SOURCE)), 'functions':[{ 'name':n.name,'line':n.lineno} for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef))], 'imports':[ast.unparse(n) for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]})
    f=rectangle();a,b=box(),box((10,0,0));op=Mock();op.IsDone.return_value=False
    with patch.object(m,'_common_operation',return_value=op):
        r=m.intersect_face_patches(f,f)
        not_done=dict(completed=r.completed,patch_count=len(r.patches))
    with patch.object(m,'_common_operation',side_effect=RuntimeError('injected native failure')):
        try:m.intersect_face_patches(f,f)
        except Exception as exc:raised=dict(type=type(exc).__name__,stage=getattr(exc,'stage',None),message=str(exc))
    with patch.object(m,'intersect_face_patches',return_value=m.FacePatchIntersection(False,())):
        ignored=m.measure_planar_contact_area(a,b)
    manifest=json.loads((CAD/'backend/tests/fixtures/fixtures-manifest.json').read_text())
    inputs=[record(p) for p in external_inputs().values()]
    for name in ['solid-sheet','real-gearbox']:
        expected=manifest['fixtures'][name.replace('-','_')]['sha256']
        assert record(external_inputs()[name])['sha256']==expected
    revision=subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()
    assert revision=='29fecb3bc55e114c766b1553b86d8adaa85dbca5'
    result=dict(status='pass',source_root=str(SOURCE),source_revision=revision,sources=sources,inputs=inputs,
        language='Python/CadQuery/OCP orchestration calls existing OCCT C++ BRepExtrema_DistShapeShape and BRepAlgoAPI_Common; no new native backend or legacy service invocation',
        call_chain=['geometry._exact_pair_in_process -> solid_pairs.measure_shape_pair -> OCP distance/common -> planar scan -> intersect_face_patches','modeling.exposed_region_faces -> intersect_face_patches(fuzzy=None); false => existing Chinese ValueError','modeling.contact_candidates -> intersect_face_patches(fuzzy=None); false => partial; TC-/patch IDs, budget, rounding and publication remain caller-owned'],
        observed_source_failures=dict(not_done=not_done,thrown_patch_exception=raised,failed_planar_pairs_return=ignored,budget_exhausted_return=m.measure_planar_contact_area(a,b,maximum_face_pairs=0)),
        license='S has no root LICENSE/COPYING. Internal extraction authorized by user; no public redistribution grant inferred. Dependencies retain B02 license assessment; B15 release review required.')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'source-provenance.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'pass','source_files':len(sources),'external_inputs':len(inputs)}))

if __name__=='__main__':audit()
