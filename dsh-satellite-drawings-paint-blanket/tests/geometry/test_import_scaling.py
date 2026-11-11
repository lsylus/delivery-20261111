import json
import cadquery as cq
import pytest
import numpy as np
from geometry_core.xcaf import read_xcaf_source, XcafReadOptions
from geometry_core.snapshot import load_model_snapshot
from geometry_core.tessellation import face_refs


def legacy_adjacency(shape):
    edges=[face.Edges() for face in shape.Faces()]
    return [[f'face-{j+1}' for j,other in enumerate(edges) if j!=i and any(a.isSame(b) for a in current for b in other)] for i,current in enumerate(edges)]


@pytest.mark.parametrize('kind',['box','cylinder','touching','compound','hole'])
@pytest.mark.parametrize('collide',[False,True])
def test_indexed_adjacency_matches_native_pairwise_oracle(kind,collide,monkeypatch):
    box=cq.Workplane().box(10,20,30).val()
    shapes=dict(box=box,cylinder=cq.Workplane().cylinder(20,5).val(),
                touching=cq.Compound.makeCompound([box,box.translate((10,0,0))]),
                compound=cq.Compound.makeCompound([box,box.rotate((0,0,0),(0,0,1),33).translate((40,0,0))]),
                hole=cq.Workplane().box(10,20,30).faces('>Z').workplane().hole(3).val())
    shape=shapes[kind]
    expected=legacy_adjacency(shape)
    if collide:monkeypatch.setattr(cq.Edge,'hashCode',lambda edge:1)
    faces,refs=face_refs(shape,{},'occ-1')
    assert [r['signature']['adjacency'] for r in refs]==expected
    assert [r['entity_id'] for r in refs]==[f'face-{i+1}' for i in range(len(faces))]


@pytest.mark.parametrize('name,unit',[('box-100','mm'),('inch-box','inch')])
def test_snapshot_reuses_xcaf_units_without_second_read(name,unit,fixtures,tmp_path,monkeypatch):
    from geometry_core import serialization
    original=serialization.read_step_summary
    graph=read_xcaf_source(fixtures/f'{name}.step')
    assert graph.source_length_units==original(fixtures/f'{name}.step').length_units
    def forbidden(*args,**kwargs):raise AssertionError('snapshot must not parse/transfer STEP twice')
    monkeypatch.setattr(serialization,'read_step_summary',forbidden)
    snapshot=load_model_snapshot(fixtures/f'{name}.step',project_id='p',model_id='m',model_revision=1,asset_id='a',output_dir=tmp_path/'output')
    assert snapshot['source_manifest']['units']==unit
    assert snapshot['units']=='mm'


def test_snapshot_geometry_only_transfer_keeps_assembly_and_names(fixtures):
    full=read_xcaf_source(fixtures/'assembly-tree.step')
    lean=read_xcaf_source(fixtures/'assembly-tree.step',options=XcafReadOptions(read_colors=False,read_layers=False,read_metadata=False))
    assert lean.nodes==full.nodes
    assert lean.root_keys==full.root_keys
    assert lean.source_length_units==full.source_length_units
    for node in full.nodes:
        a=cq.Shape.cast(full.geometry(node.key).world_shape)
        b=cq.Shape.cast(lean.geometry(node.key).world_shape)
        assert len(a.Faces())==len(b.Faces())
        assert a.Volume()==pytest.approx(b.Volume(),rel=1e-10)
        assert a.Center().toTuple()==pytest.approx(b.Center().toTuple(),abs=1e-10)


def test_merged_occurrence_ranges_select_every_face_boundary(graph,model_ref,tmp_path):
    import copy
    from contracts import validate
    from jsonschema import ValidationError
    from geometry_core.tessellation import tessellate_with_face_map,resolve_face
    from test_face_mesh_map import arrays
    small=tessellate_with_face_map(graph,model_ref,tmp_path/'small')
    merged=tessellate_with_face_map(graph,model_ref,tmp_path/'merged',merge_face_threshold=0)
    a=json.loads((tmp_path/'small/mesh-map.json').read_text())
    b=json.loads((tmp_path/'merged/mesh-map.json').read_text());validate('mesh-map',b)
    assert [e['face_ref'] for e in a['faces']]==[e['face_ref'] for e in b['faces']]
    assert small['triangle_count']==merged['triangle_count']
    document,get=arrays(tmp_path/'merged/model.glb')
    assert all(len(mesh['primitives'])==1 for mesh in document['meshes'])
    for mesh_index,mesh in enumerate(document['meshes']):
        primitive=mesh['primitives'][0];positions=get(primitive['attributes']['POSITION']);indices=get(primitive['indices']).reshape(-1,3)
        ranges=[e for e in b['faces'] if e['mesh']==mesh_index]
        assert ranges[0]['triangle_start']==0
        assert sum(e['triangle_count'] for e in ranges)==len(indices)
        for entry in ranges:
            start=entry['triangle_start'];end=start+entry['triangle_count']
            for triangle in (start,end-1):
                assert resolve_face(b,model_ref=model_ref,glb_sha256=b['glb_sha256'],node=entry['node'],mesh=mesh_index,primitive=0,triangle=triangle)==entry['face_ref']
            triangles=positions[indices[start:end]]
            area=sum(__import__('numpy').linalg.norm(__import__('numpy').cross(y-x,z-x))/2 for x,y,z in triangles)
            assert area==pytest.approx(entry['face_ref']['signature']['area_mm2'],rel=1e-6)
        with pytest.raises(ValueError):
            resolve_face(b,model_ref=model_ref,glb_sha256=b['glb_sha256'],node=ranges[0]['node'],mesh=mesh_index,primitive=0,triangle=len(indices))
    overlap=copy.deepcopy(b);overlap['faces'][1]['triangle_start']=0
    with pytest.raises(ValidationError,match='overlapping'):validate('mesh-map',overlap)


def test_vector_triangle_payload_matches_scalar_order_normals_and_collapse():
    from geometry_core.tessellation import _triangle_payload
    random=np.random.default_rng(17)
    coordinates=random.normal(size=(60,3));coordinates[1]=coordinates[0]
    points=[cq.Vector(*p) for p in coordinates]
    triangles=[(i,i+1,i+2) for i in range(2,57,3)]+[(0,1,2)]
    expected_positions=[];expected_normals=[];expected_emitted=[];expected_collapsed=[];area=0.
    for index,triangle in enumerate(triangles):
        xyz=np.asarray([points[i].toTuple() for i in triangle]);normal=np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]);norm=np.linalg.norm(normal)
        if norm==0:
            expected_collapsed.append(dict(source_triangle=index,node_ids=list(triangle),points_mm=xyz.tolist(),twice_area_mm2=0.,reason='exact_duplicate_coordinates'));continue
        expected_positions.extend(xyz.tolist());expected_normals.extend([list(normal/norm)]*3);expected_emitted.append(index);area+=norm/2
    positions,normals,collapsed,emitted,actual_area=_triangle_payload(points,triangles)
    assert np.array_equal(positions,np.asarray(expected_positions))
    assert np.allclose(normals,np.asarray(expected_normals),rtol=1e-14,atol=1e-15)
    assert collapsed==expected_collapsed and emitted==expected_emitted
    assert actual_area==pytest.approx(area,rel=1e-14)


@pytest.mark.parametrize('third',[(1.,1e-16,0.),(2.,0.,0.)])
def test_vector_triangle_payload_retains_distinct_near_degenerate_rejection(third):
    from geometry_core.tessellation import _triangle_payload
    with pytest.raises(ValueError,match='degenerate tessellation triangle'):
        _triangle_payload([cq.Vector(0,0,0),cq.Vector(1,0,0),cq.Vector(*third)],[(0,1,2)])
