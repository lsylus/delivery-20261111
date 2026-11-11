"""Produce actual STEP/BRep/GLB evidence. Failure leaves a non-passing record."""
from dataclasses import asdict
import importlib.metadata, json, platform, sys
from pathlib import Path
import cadquery as cq
from geometry_core import load_model_snapshot
from geometry_core.xcaf import read_xcaf_source
from geometry_core.serialization import read_step_summary, write_step_graph, inspect_step
from geometry_core.hashing import file_sha256
from geometry_core.glb_serialization import read_glb_summary
from contracts import validate
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/B02'
def record(p):return {'path':str(p.relative_to(ROOT)),'sha256':file_sha256(p),'bytes':p.stat().st_size}
def main():
    result={'status':'failed','inputs':[],'artifacts':[],'cases':[]}
    try:
        manifest=json.loads((ROOT/'fixtures/synthetic/geometry-manifest.json').read_text())
        for f in manifest['files']:
            p=ROOT/'fixtures/synthetic'/f['path']
            assert file_sha256(p)==f['sha256'] and p.stat().st_size==f['bytes']
            result['inputs'].append(record(p))
        for name in ('assembly-tree','inch-box','concave','panel-opening'):
            source=ROOT/f'fixtures/synthetic/{name}.step'
            dest=OUT/'artifacts'/name
            graph=read_xcaf_source(source)
            snapshot=load_model_snapshot(source,project_id='b02-acceptance',model_id=name,model_revision=1,asset_id=name,output_dir=dest)
            validate('model',snapshot,'ModelSnapshot')
            mesh_map=json.loads((dest/'mesh-map.json').read_text());validate('mesh-map',mesh_map)
            exported=write_step_graph(graph,dest/'roundtrip.step')
            back=read_xcaf_source(exported)
            assert len(back.nodes)==len(graph.nodes) and len(back.leaves)==len(graph.leaves)
            facts=read_step_summary(exported)
            assert facts.topology.valid
            original=read_step_summary(source)
            assert abs(facts.volume_mm3-original.volume_mm3)<=max(abs(original.volume_mm3)*1e-6,1e-9)
            assert max(abs(a-b) for a,b in zip(facts.bounds.values,original.bounds.values))<=1e-6
            for definition in snapshot['definitions']:
                assert cq.Shape.importBrep(str(dest/definition['shape_asset'])).isValid()
            result['cases'].append({'name':name,'instances':len(graph.nodes),'leaves':len(graph.leaves),'readback':asdict(facts),'glb':asdict(read_glb_summary(dest/'model.glb'))})
            result['artifacts'].extend(record(p) for p in sorted(dest.rglob('*')) if p.is_file())
        inventory=json.loads((ROOT/'fixtures/manifests/real-gearbox.inventory.json').read_text())
        external=Path(inventory['source_root'])/inventory['files'][0]['relative_path']
        assert file_sha256(external)==inventory['files'][0]['sha256']
        result['inputs'].append({'path':str(external),'sha256':file_sha256(external),'bytes':external.stat().st_size})
        result['real_external_scope']='real-gearbox source/new parser equivalence only; no manufactured truth, holdouts untouched'
        for name in ('assembly-tree','concave','inch-box','real-gearbox'):
            folder=OUT/'characterization'/name
            old=json.loads((folder/'source.json').read_text());new=json.loads((folder/'new.json').read_text())
            assert new['step'].pop('completed');new['step'].pop('volume_mm3')
            assert old==new
            result['artifacts'].extend(record(folder/f'{mode}.json') for mode in ('source','new'))
        result['status']='pass'
    except Exception as exc:
        result['error']=f'{type(exc).__name__}: {exc}'
        raise
    finally:
        (OUT/'readback.json').write_text(json.dumps(result,indent=2)+'\n')
        env={'status':'pass','python':sys.version,'platform':platform.platform(),'machine':platform.machine(),
             'packages':{p:importlib.metadata.version(p) for p in ('cadquery','cadquery-ocp','numpy','pytest','jsonschema')},
             'native':'CadQuery/OCP uses existing OCCT C++; no new kernel; production imports have no S/H dependency'}
        (OUT/'environment.json').write_text(json.dumps(env,indent=2)+'\n')
    return 0
if __name__=='__main__':raise SystemExit(main())
