import copy,json,struct
import numpy as np
import pytest
from geometry_core.tessellation import tessellate_with_face_map,resolve_face
from geometry_core.glb_serialization import read_glb
from geometry_core.hashing import file_sha256
from contracts import validate

def arrays(path):
    raw=path.read_bytes();length=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+length]);start=20+length
    blob=raw[start+8:]
    def get(i):
        a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']]
        dims=3 if a['type']=='VEC3' else 1
        x=np.frombuffer(blob,dtype='<f4' if a['componentType']==5126 else '<u4',count=a['count']*dims,offset=v.get('byteOffset',0)+a.get('byteOffset',0))
        return x.reshape((-1,dims)) if dims==3 else x
    return doc,get

def test_every_rendered_triangle_selects_actual_current_face(graph,model_ref,tmp_path):
    result=tessellate_with_face_map(graph,model_ref,tmp_path)
    mapping=json.loads((tmp_path/'mesh-map.json').read_text());validate('mesh-map',mapping)
    doc,get=arrays(tmp_path/'model.glb')
    assert result['triangle_count']==38 and len(mapping['faces'])==19
    assert len(doc['meshes'])==3
    for entry in mapping['faces']:
        ref=entry['face_ref'];validate('mesh-map',ref,'FaceRef')
        assert ref['model_revision']==1
        primitive=doc['meshes'][entry['mesh']]['primitives'][entry['primitive']]
        pos=get(primitive['attributes']['POSITION']);indices=get(primitive['indices']);normal=get(primitive['attributes']['NORMAL'])
        assert len(indices)==3*entry['triangle_count'] and max(indices)<len(pos)
        total=0
        for i,tri in enumerate(indices.reshape(-1,3)):
            a,b,c=pos[tri];cross=np.cross(b-a,c-a);total+=np.linalg.norm(cross)/2
            assert np.dot(cross,normal[tri[0]])>0
            assert resolve_face(mapping,model_ref=model_ref,glb_sha256=file_sha256(tmp_path/'model.glb'),node=entry['node'],mesh=entry['mesh'],primitive=entry['primitive'],triangle=i)==ref
        assert total==pytest.approx(ref['signature']['area_mm2'],rel=1e-6)
        assert np.mean(pos,axis=0)==pytest.approx(ref['signature']['centroid_mm'],abs=1e-6)
    a=[e for e in mapping['faces'] if e['face_ref']['instance_id']=='occ-1-1-1']
    b=[e for e in mapping['faces'] if e['face_ref']['instance_id']=='occ-1-1-2']
    assert len(a)==len(b)==6 and a[0]['face_ref']['signature']!=b[0]['face_ref']['signature']
    assert read_glb(tmp_path/'model.glb').readback.triangle_count==result['triangle_count']

@pytest.mark.parametrize('change',['revision','digest','glb','triangle','primitive'])
def test_stale_and_invalid_selection_rejected(graph,model_ref,tmp_path,change):
    tessellate_with_face_map(graph,model_ref,tmp_path)
    mapping=json.loads((tmp_path/'mesh-map.json').read_text());entry=mapping['faces'][0]
    args=dict(model_ref=copy.deepcopy(model_ref),glb_sha256=mapping['glb_sha256'],node=entry['node'],mesh=entry['mesh'],primitive=entry['primitive'],triangle=0)
    if change=='revision':args['model_ref']['model_revision']=2
    elif change=='digest':args['model_ref']['assembly_digest']='a'*64
    elif change=='glb':args['glb_sha256']='0'*64
    elif change=='triangle':args['triangle']=entry['triangle_count']
    else:args['primitive']=999
    with pytest.raises(ValueError):resolve_face(mapping,**args)

def test_tessellation_is_repeatable_and_source_stays_unchanged(graph,model_ref,tmp_path):
    before=file_sha256(graph.source)
    a=tessellate_with_face_map(graph,model_ref,tmp_path/'a')
    b=tessellate_with_face_map(graph,model_ref,tmp_path/'b')
    assert a==b and file_sha256(graph.source)==before
    with pytest.raises(ValueError):tessellate_with_face_map(graph,model_ref,tmp_path/'bad',tolerance_mm=0)

def test_hole_and_curved_faces_have_complete_maps(fixtures,tmp_path):
    from geometry_core import load_model_snapshot
    for name in ('panel-opening','paint-plate-0'):
        out=tmp_path/name
        s=load_model_snapshot(fixtures/f'{name}.step',project_id='p',model_id=name,model_revision=1,asset_id='a',output_dir=out)
        mapping=json.loads((out/'mesh-map.json').read_text());validate('mesh-map',mapping)
        doc,get=arrays(out/'model.glb')
        for e in mapping['faces']:
            p=doc['meshes'][e['mesh']]['primitives'][e['primitive']]
            positions=get(p['attributes']['POSITION']); indices=get(p['indices']).reshape(-1,3)
            assert len(indices)==e['triangle_count']>0
            if name=='panel-opening':
                centroids=np.mean(positions[indices],axis=1)
                assert not any(40<x<60 and 30<y<50 for x,y,z in centroids)
                areas=[np.linalg.norm(np.cross(b-a,c-a))/2 for a,b,c in positions[indices]]
                assert sum(areas)==pytest.approx(7600,rel=1e-6)
        if name.startswith('paint'):
            curved=[e for e in mapping['faces'] if e['face_ref']['signature']['type']=='CYLINDER']
            assert len(curved)==2 and all(e['face_ref']['signature']['normal'] is None for e in curved)

def test_mismatched_source_and_invalid_mesh_map_rejected(graph,model_ref,tmp_path):
    from jsonschema import ValidationError
    with pytest.raises(ValueError):
        tessellate_with_face_map(graph,{**model_ref,'assembly_digest':'0'*64},tmp_path/'bad')
    tessellate_with_face_map(graph,model_ref,tmp_path/'good')
    mapping=json.loads((tmp_path/'good/mesh-map.json').read_text())
    bad=copy.deepcopy(mapping);bad['faces'][0]['face_ref']['model_revision']=2
    with pytest.raises(ValidationError):validate('mesh-map',bad)
    bad=copy.deepcopy(mapping);bad['faces'].append(bad['faces'][0])
    with pytest.raises(ValidationError):validate('mesh-map',bad)

def test_changed_source_invalidates_loaded_graph(fixtures,tmp_path):
    from geometry_core.xcaf import read_xcaf_source
    from geometry_core.hashing import digest_files
    source=tmp_path/'source.step';source.write_bytes((fixtures/'box-100.step').read_bytes())
    graph=read_xcaf_source(source)
    source.write_bytes((fixtures/'concave.step').read_bytes())
    ref={'project_id':'p','model_id':'m','model_revision':1,'assembly_digest':digest_files([{'relative_path':source.name,'sha256':file_sha256(source),'bytes':source.stat().st_size}])}
    with pytest.raises(ValueError,match='source changed'):
        tessellate_with_face_map(graph,ref,tmp_path/'mesh')
