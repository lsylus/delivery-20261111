import json
import cadquery as cq
import numpy as np
import pytest
from geometry_core.tessellation import tessellate_with_face_map,face_refs,instance_id,resolve_face
from contracts import validate
from test_face_mesh_map import arrays


@pytest.mark.parametrize('merge_threshold',[0,50000])
def test_shared_definition_buffers_keep_world_geometry_and_instance_selection(graph,model_ref,tmp_path,merge_threshold):
    baseline=tmp_path/'baseline';shared=tmp_path/'shared'
    before=tessellate_with_face_map(graph,model_ref,baseline,merge_face_threshold=merge_threshold)
    after=tessellate_with_face_map(graph,model_ref,shared,merge_face_threshold=merge_threshold,reuse_definition_meshes=True)
    old,old_get=arrays(baseline/'model.glb');document,get=arrays(shared/'model.glb')
    mapping=json.loads((shared/'mesh-map.json').read_text());validate('mesh-map',mapping)
    old_mapping=json.loads((baseline/'mesh-map.json').read_text())
    audit=json.loads((shared/'tessellation-audit.json').read_text())
    assert before['triangle_count']==after['triangle_count']==38
    assert len(old['meshes'])==3 and len(document['meshes'])==2
    assert document['buffers'][0]['byteLength']<old['buffers'][0]['byteLength']
    assert audit['shared_definition_meshes']==1 and audit['glb_meshes']==2
    assert document['nodes'][0]['matrix']==old['nodes'][0]['matrix']
    reused=[]
    for leaf in graph.leaves:
        occurrence=instance_id(leaf.key)
        _,expected=face_refs(cq.Shape.cast(graph.geometry(leaf.key).world_shape),model_ref,occurrence)
        entries=[entry for entry in mapping['faces'] if entry['face_ref']['instance_id']==occurrence]
        node=document['nodes'][entries[0]['node']]
        matrix=np.asarray(node.get('matrix',np.eye(4).flatten(order='F'))).reshape((4,4),order='F')
        if 'matrix' in node:
            reused.append(node)
            assert matrix[:3,:3]==pytest.approx(np.asarray(leaf.world_transform.rotation))
            assert matrix[:3,3]==pytest.approx(leaf.world_transform.translation_mm)
        for entry,oracle in zip(entries,expected):
            assert entry['mesh']==node['mesh']
            ref=entry['face_ref']
            assert ref['instance_id']==occurrence and ref['entity_id']==oracle['entity_id']
            assert ref['signature']['centroid_mm']==pytest.approx(oracle['signature']['centroid_mm'],abs=1e-9)
            assert ref['signature']['normal']==pytest.approx(oracle['signature']['normal'],abs=1e-9)
            primitive=document['meshes'][entry['mesh']]['primitives'][entry['primitive']]
            positions=get(primitive['attributes']['POSITION']);normals=get(primitive['attributes']['NORMAL'])
            indices=get(primitive['indices']).reshape(-1,3)
            start=entry['triangle_start'];end=start+entry['triangle_count']
            xyz=positions[indices[start:end]]@matrix[:3,:3].T+matrix[:3,3]
            world_normals=normals[indices[start:end]]@matrix[:3,:3].T
            old_entry=next(e for e in old_mapping['faces'] if e['face_ref']['instance_id']==occurrence and e['face_ref']['entity_id']==ref['entity_id'])
            old_primitive=old['meshes'][old_entry['mesh']]['primitives'][old_entry['primitive']]
            old_xyz=old_get(old_primitive['attributes']['POSITION'])[old_get(old_primitive['indices']).reshape(-1,3)[start:end]]
            assert xyz==pytest.approx(old_xyz,abs=2e-5)
            cross=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])
            assert np.all(np.sum(cross*world_normals[:,0],axis=1)>0)
            assert np.linalg.norm(cross,axis=1).sum()/2==pytest.approx(oracle['signature']['area_mm2'],rel=1e-6)
            for triangle in (start,end-1):
                assert resolve_face(mapping,model_ref=model_ref,glb_sha256=mapping['glb_sha256'],node=entry['node'],mesh=entry['mesh'],primitive=entry['primitive'],triangle=triangle)==ref
    assert len(reused)==2 and reused[0]['mesh']==reused[1]['mesh']
    assert reused[0]['matrix']!=reused[1]['matrix']


def test_explicit_disabled_sharing_preserves_small_display_structure(graph,model_ref,tmp_path):
    tessellate_with_face_map(graph,model_ref,tmp_path,reuse_definition_meshes=False)
    document,_=arrays(tmp_path/'model.glb')
    assert len(document['meshes'])==3
    assert all('matrix' not in node for node in document['nodes'][1:])
