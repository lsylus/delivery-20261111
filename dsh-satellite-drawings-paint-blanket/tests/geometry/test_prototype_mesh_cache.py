import json
import numpy as np
import cadquery as cq
import pytest
from geometry_core.tessellation import tessellate_with_face_map,face_refs,instance_id,resolve_face
from test_face_mesh_map import arrays


def test_repeated_definitions_mesh_once_and_keep_world_face_identity(graph,model_ref,tmp_path,monkeypatch):
    original=cq.Face.tessellate
    calls=[]
    def counted(face,*args,**kwargs):
        calls.append(face)
        return original(face,*args,**kwargs)
    monkeypatch.setattr(cq.Face,'tessellate',counted)
    tessellate_with_face_map(graph,model_ref,tmp_path,merge_face_threshold=0)
    unique={}
    for leaf in graph.leaves:
        unique.setdefault(leaf.definition_label_entry,len(cq.Shape.cast(graph.geometry(leaf.key).world_shape).Faces()))
    assert len(calls)==sum(unique.values())
    mapping=json.loads((tmp_path/'mesh-map.json').read_text())
    audit=json.loads((tmp_path/'tessellation-audit.json').read_text())
    assert audit['prototype_meshes']==len(unique)
    document,get=arrays(tmp_path/'model.glb')
    for leaf in graph.leaves:
        _,expected=face_refs(cq.Shape.cast(graph.geometry(leaf.key).world_shape),model_ref,instance_id(leaf.key))
        entries=[e for e in mapping['faces'] if e['face_ref']['instance_id']==instance_id(leaf.key)]
        assert len(entries)==len(expected)
        for entry,oracle in zip(entries,expected):
            ref=entry['face_ref']
            assert {k:v for k,v in ref.items() if k!='signature'}=={k:v for k,v in oracle.items() if k!='signature'}
            for field in ('type','adjacency'):assert ref['signature'][field]==oracle['signature'][field]
            for field in ('area_mm2','centroid_mm','normal'):
                value=oracle['signature'][field]
                if value is None:assert ref['signature'][field] is None
                else:assert ref['signature'][field]==pytest.approx(value,rel=1e-10,abs=1e-9)
            primitive=document['meshes'][entry['mesh']]['primitives'][entry['primitive']]
            positions=get(primitive['attributes']['POSITION'])
            triangles=get(primitive['indices']).reshape(-1,3)
            start=entry['triangle_start'];end=start+entry['triangle_count']
            xyz=positions[triangles[start:end]]
            measured=np.linalg.norm(np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0]),axis=1).sum()/2
            assert measured==pytest.approx(oracle['signature']['area_mm2'],rel=1e-6)
            for triangle in (start,end-1):
                assert resolve_face(mapping,model_ref=model_ref,glb_sha256=mapping['glb_sha256'],node=entry['node'],mesh=entry['mesh'],primitive=entry['primitive'],triangle=triangle)==ref
