from b08_cases import assembly, box, from_shapes
from thermal_drawings.paint.recommendations import recommend


def selected(result, instance_id):
    return [group for group in result['groups'] if group['instance_id']==instance_id and group['recommended']]


def test_plate_recommends_both_exact_opposite_broad_faces():
    model=from_shapes([box(0,0,0,100,80,5)])
    result=recommend(model,'revision-1',{'occ-0':'panel'})
    assert result['status']=='passed' and result['revision_id']=='revision-1'
    groups=selected(result,'occ-0')
    assert len(groups)==2
    assert {group['direction_label'] for group in groups}=={'+Z','-Z'}
    assert {group['side_label'] for group in groups}=={'side-a','side-b'}
    assert groups[0]['opposite_group_id']==groups[1]['group_id']
    assert groups[1]['opposite_group_id']==groups[0]['group_id']
    assert all(group['instance_name']=='panel' and group['selectable'] for group in groups)
    assert all(group['default_paint_type']=='unassigned' for group in groups)
    assert all(ref['project_id']==model.model_ref['project_id'] and ref['model_revision']==model.model_ref['model_revision']
               for group in groups for ref in group['target_face_refs'])


def test_small_box_components_are_not_default_paint_panels():
    result=recommend(assembly(),'revision-2')
    assert len(selected(result,'occ-0'))==2
    assert selected(result,'occ-1')==[]
    assert selected(result,'occ-2')==[]
    assert all(group['topology_status']=='valid' for group in result['groups'])


def test_assembly_major_surfaces_demote_large_faces_on_internal_components():
    body=box(0,0,0,1000,800,100)
    internal_a=box(100,100,20,500,400,20)
    internal_b=box(200,200,50,450,350,20)
    result=recommend(from_shapes([body,internal_a,internal_b]),'revision-major',
                     {'occ-0':'body','occ-1':'payload-a','occ-2':'payload-b'})
    assert len(selected(result,'occ-0'))==2
    assert selected(result,'occ-1')==[]
    assert selected(result,'occ-2')==[]
    assert all('assembly_major_body_surface' in group['confidence']['reasons']
               for group in selected(result,'occ-0'))
    assert any('not_assembly_major_body_surface' in group['confidence']['reasons']
               for group in result['groups'] if group['instance_id']!='occ-0')


def test_multiwall_component_does_not_require_component_level_plate_ratio():
    walls=box(0,0,0,5,100,80).fuse(
        box(95,0,0,5,100,80),
        box(5,0,0,90,5,80),
        box(5,95,0,90,5,80),
    ).clean()
    result=recommend(from_shapes([walls]),'revision-walls',{'occ-0':'Walls_part'})
    groups=selected(result,'occ-0')
    assert {group['direction_label'] for group in groups}>={'+X','-X','+Y','-Y'}
    maximum=max(group['area_mm2'] for group in result['groups'] if group['selectable'])
    assert all(group['area_mm2']>=maximum*.5 for group in groups)
    assert all('assembly_major_body_surface' in group['confidence']['reasons'] for group in groups)
    assert any('plate_thickness_ratio=0.800000' in group['confidence']['reasons'] for group in groups)


def test_recommendations_are_deterministic_and_planar_only():
    model=assembly(features=True)
    first=recommend(model,'revision-3')
    second=recommend(model,'revision-3')
    assert first==second
    assert first['groups']
    assert all(ref['signature']['type']=='PLANE' for group in first['groups'] for ref in group['target_face_refs'])
    assert len({group['group_id'] for group in first['groups']})==len(first['groups'])
