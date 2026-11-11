from dataclasses import replace
import json
import cadquery as cq
import pytest
from OCP.TopLoc import TopLoc_Location
from geometry_core.xcaf import XcafNodeGeometry
from geometry_core.transforms import rigid_transform_from_location
from geometry_core.tessellation import tessellate_with_face_map
from geometry_core.hashing import file_sha256
from geometry_core.glb_serialization import read_glb_summary
from contracts import validate
from test_display_remesh import zero_measure_planar_face


def test_zero_measure_face_keeps_native_identity_without_fake_display_triangles(graph,model_ref,tmp_path):
    source_hash=file_sha256(graph.source)
    collapsed=zero_measure_planar_face()
    native=cq.Compound.makeCompound([cq.Solid.makeBox(10,20,30),collapsed]).wrapped
    source_validity=cq.Shape.cast(native).isValid()
    location=TopLoc_Location();identity=rigid_transform_from_location(location)
    node=replace(graph.leaves[0],key=(1,),parent_key=None,child_keys=(),depth=0,
                 definition_label_entry='catalog-test',local_transform=identity,world_transform=identity)
    geometry=XcafNodeGeometry(native,native,native,location,location)
    test_graph=replace(graph,nodes=(node,),root_keys=(node.key,),_geometry_by_key={node.key:geometry})
    tessellate_with_face_map(test_graph,model_ref,tmp_path)
    mapping=json.loads((tmp_path/'mesh-map.json').read_text());validate('mesh-map',mapping)
    audit=json.loads((tmp_path/'tessellation-audit.json').read_text())
    assert len(mapping['faces'])==6 and len(mapping['unrenderable_faces'])==1
    entry=mapping['unrenderable_faces'][0]
    assert entry['face_ref']['instance_id']=='occ-1' and entry['face_ref']['entity_id']=='face-7'
    assert entry['diagnostic']['native_retained'] is True
    assert entry['diagnostic']['native_valid'] is collapsed.isValid()
    assert audit['native_faces']==7 and audit['mapped_faces']==6
    assert audit['unrenderable_native_faces']==1 and audit['dropped_native_faces']==0
    assert read_glb_summary(tmp_path/'model.glb').triangle_count==12
    # Source CAD is not repaired or stripped to manufacture a successful import.
    assert len(cq.Shape.cast(test_graph.geometry(node.key).world_shape).Faces())==7
    assert cq.Shape.cast(native).isValid() is source_validity
    assert file_sha256(graph.source)==source_hash


def test_nonzero_unmeshed_face_still_fails_instead_of_silent_omission(graph,model_ref,tmp_path,monkeypatch):
    monkeypatch.setattr(cq.Face,'tessellate',lambda face,*args,**kwargs:([],[]))
    with pytest.raises(ValueError,match='face has no triangles'):
        tessellate_with_face_map(graph,model_ref,tmp_path)
    assert not (tmp_path/'mesh-map.json').exists()


def test_single_unmeshed_nonzero_face_is_explicit_while_other_faces_remain_selectable(graph,model_ref,tmp_path,monkeypatch):
    original=cq.Face.tessellate;target=[]
    def signature(face):
        return (face.geomType(),round(face.Area(),9),tuple(round(x,9) for x in face.Center().toTuple()))
    def unavailable(face,*args,**kwargs):
        current=signature(face)
        if not target:target.append(current)
        if current==target[0]:return [],[]
        return original(face,*args,**kwargs)
    monkeypatch.setattr(cq.Face,'tessellate',unavailable)
    before=[len(cq.Shape.cast(graph.geometry(leaf.key).world_shape).Faces()) for leaf in graph.leaves]
    tessellate_with_face_map(graph,model_ref,tmp_path)
    mapping=json.loads((tmp_path/'mesh-map.json').read_text());validate('mesh-map',mapping)
    audit=json.loads((tmp_path/'tessellation-audit.json').read_text())
    assert mapping['faces'] and mapping['unrenderable_faces']
    assert len(mapping['faces'])+len(mapping['unrenderable_faces'])==sum(before)
    for entry in mapping['unrenderable_faces']:
        assert entry['face_ref']['signature']['area_mm2']>0
        assert entry['diagnostic']['reason']=='native_mesher_failure'
        assert entry['diagnostic']['native_retained'] is True
        assert entry['diagnostic']['native_valid'] is True
    assert audit['native_faces']==sum(before) and audit['dropped_native_faces']==0
    assert read_glb_summary(tmp_path/'model.glb').triangle_count>0
    assert [len(cq.Shape.cast(graph.geometry(leaf.key).world_shape).Faces()) for leaf in graph.leaves]==before
