import os,tempfile,json
from pathlib import Path
from b12_workflow import ROOT,exercise
out=ROOT/os.environ.get('B12_EVIDENCE_DIR','docs/evidence/B12');out.mkdir(parents=True,exist_ok=True)
base=Path(tempfile.mkdtemp(prefix='b12-workflow-',dir=ROOT/'work'))
try:
    from extract_b12_equipment import SOURCE,metrics
    from geometry_core.xcaf import read_xcaf_source
    import hashlib,cadquery as cq
    manifest=json.loads((ROOT/'fixtures/manifests/blanket_cases.json').read_text())
    derived=ROOT/manifest['derived_path']
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==manifest['source_sha256'] and hashlib.sha256(derived.read_bytes()).hexdigest()==manifest['derived_sha256']
    source_graph=read_xcaf_source(SOURCE);derived_graph=read_xcaf_source(derived)
    for item in manifest['equipment']:
        for graph,key,label in [(source_graph,item['source_key'],'metrics'),(derived_graph,item['derived_key'],'derived_metrics')]:
            observed=metrics(cq.Shape.cast(graph.geometry(tuple(key)).world_shape));expected=item[label]
            assert observed['faces']==expected['faces']==6
            for field in ['volume_mm3','area_mm2']:assert abs(observed[field]-expected[field])<=max(1e-6,abs(expected[field])*1e-9)
            assert max(abs(a-b) for a,b in zip(observed['bounds_mm'],expected['bounds_mm']))<1e-6
    (out/'source-provenance.json').write_text(json.dumps(dict(status='pass',source_sha256=manifest['source_sha256'],derived_sha256=manifest['derived_sha256'],instances_verified=4,scope=manifest['scope']),indent=2)+'\n')
    record=exercise(base/'service',out/'artifacts');(out/'workflow.json').write_text(json.dumps(record,indent=2)+'\n')
finally:
    base.rmdir()
print('B12 real HTTP, source/BRep bundle, document and actual DWG: passed')
