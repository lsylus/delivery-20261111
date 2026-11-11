import json, os, subprocess, sys
from pathlib import Path
import cadquery as cq
import pytest
from geometry_core.xcaf import read_xcaf_source
from geometry_core import load_model_snapshot
from geometry_core.topology import measure_shape_topology
from geometry_core.hashing import file_sha256
from contracts import validate
ROOT=Path(__file__).resolve().parents[2]

@pytest.mark.parametrize('case',['assembly-tree','concave','inch-box','real-gearbox'])
def test_source_new_independent_process_equivalence(case,fixtures,tmp_path):
    if case=='real-gearbox':
        inventory=json.loads((ROOT/'fixtures/manifests/real-gearbox.inventory.json').read_text())
        item=inventory['files'][0]; source=Path(inventory['source_root'])/item['relative_path']
        assert file_sha256(source)==item['sha256']
    else: source=fixtures/f'{case}.step'
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};env.pop('PYTHONPATH',None)
    tmp_path=ROOT/'docs/evidence/B02/characterization'/case
    tmp_path.mkdir(parents=True,exist_ok=True)
    for mode in ['source','new']:
        subprocess.run([sys.executable,str(ROOT/'scripts/probe_geometry.py'),mode,str(source),str(tmp_path/f'{mode}.json')],env=env,check=True,timeout=90)
    old=json.loads((tmp_path/'source.json').read_text());new=json.loads((tmp_path/'new.json').read_text())
    assert new['step'].pop('completed') is True
    volume=new['step'].pop('volume_mm3');assert volume>=0
    assert new==old

def test_tree_instances_and_analytic_placement(graph):
    assert len(graph.root_keys)==2 and len(graph.nodes)==5 and len(graph.leaves)==3
    a,b=graph.node((1,1,1)),graph.node((1,1,2))
    assert a.definition_label_entry==b.definition_label_entry
    assert a.occurrence_name=='left-foot' and b.occurrence_name=='right-foot'
    assert a.world_transform.translation_mm==pytest.approx([100,55,10],abs=1e-6)
    assert b.world_transform.translation_mm==pytest.approx([100,75,10],abs=1e-6)
    assert a.world_transform.rotation[0]==pytest.approx([0,-1,0],abs=1e-9)
    assert b.world_transform.rotation[0]==pytest.approx([-1,0,0],abs=1e-9)
    for n in (a,b):assert cq.Shape.cast(graph.geometry(n.key).world_shape).Volume()==pytest.approx(6000,rel=1e-6)
    mixed=measure_shape_topology(graph.geometry((2,)).world_shape)
    assert (mixed.solid_count,mixed.face_count,mixed.non_solid_face_count)==(1,7,1)
    assert mixed.valid

def test_retained_document_and_snapshot_brep_reopen(fixtures,tmp_path):
    import gc
    graph=read_xcaf_source(fixtures/'assembly-tree.step');gc.collect()
    from geometry_core.serialization import write_step_graph
    write_step_graph(graph,tmp_path/'after-gc.step')
    snapshot=load_model_snapshot(fixtures/'assembly-tree.step',project_id='p1',model_id='m1',model_revision=3,asset_id='a1',output_dir=tmp_path/'snapshot')
    validate('model',snapshot,'ModelSnapshot')
    assert len(snapshot['instances'])==5 and len(snapshot['definitions'])==4
    for definition in snapshot['definitions']:
        shape=cq.Shape.importBrep(str(tmp_path/'snapshot'/definition['shape_asset']))
        assert not shape.wrapped.IsNull() and shape.isValid()
    assert snapshot['instances'][2]['definition_id']==snapshot['instances'][3]['definition_id']
    assert snapshot['instances'][2]['world_transform']!=snapshot['instances'][3]['world_transform']

@pytest.mark.parametrize('name,volume,faces',[('box-100',1e6,6),('concave',525,8),('inch-box',25.4*50.8*76.2,6),('panel-opening',0,1)])
def test_fixture_analytic_oracles(fixtures,name,volume,faces):
    from geometry_core.serialization import read_step
    result=read_step(fixtures/f'{name}.step')
    assert result.readback.volume_mm3==pytest.approx(volume,rel=1e-6,abs=1e-9)
    assert result.readback.topology.face_count==faces
    if name=='panel-opening':assert result.shape.Area()==pytest.approx(7600,rel=1e-6)
    if name=='inch-box':
        assert result.readback.bounds.dimensions==pytest.approx([25.4,50.8,76.2],abs=1e-6)
        assert result.readback.length_units==('INCH',)

def test_package_has_no_legacy_application_imports():
    import ast
    import geometry_core
    for p in Path(geometry_core.__file__).parent.glob('*.py'):
        for n in ast.walk(ast.parse(p.read_text())):
            if isinstance(n,ast.Import):assert all(not a.name.startswith(('backend','thermal_drawings')) for a in n.names)
            if isinstance(n,ast.ImportFrom):assert not (n.module or '').startswith(('backend','thermal_drawings'))

@pytest.mark.parametrize('gap',[0,0.099,0.1,0.101])
def test_paint_fixture_geometry_only(fixtures,gap):
    import math
    from geometry_core.serialization import read_step
    result=read_step(fixtures/f'paint-plate-{gap:g}.step')
    assert result.readback.topology.solid_count==5
    assert result.readback.volume_mm3==pytest.approx(40000-math.pi*9*5+math.pi*16*4+160+800,rel=1e-6)
    # This only verifies generated source geometry, not B08 contact policies.
    assert result.readback.bounds.maximum[2]==pytest.approx(9+gap,abs=1e-6)
