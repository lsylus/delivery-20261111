import math
import cadquery as cq
import pytest
from b08_cases import assembly, params, box, from_shapes, override
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.paint.selection import Budget
from shapely.geometry import Polygon, Point


@pytest.mark.parametrize('gap,count,status',[(0,2,'passed'),(.099,2,'passed'),(.100,0,'needs_review'),(.101,0,'passed')])
def test_strict_gap_and_real_projection(gap,count,status):
    model=assembly(gap)
    result=generate(params(model),model,'r1')
    assert result['status']==status, result['diagnostics']
    assert len(result['regions'])==count
    for r in result['regions']:
        assert r['area_mm2']==pytest.approx(100+40*3+math.pi*9,rel=1e-6)
        assert len(r['source_refs'])==2
        evidence=r['provenance'][0]['evidence']
        assert evidence['gap_mm']==pytest.approx(gap,abs=1e-6)
        assert evidence['normal_dot']==pytest.approx(-1)
        assert evidence['common_before_projection']==(gap==0)
        assert sum(evidence['patch_areas_mm2'])==pytest.approx(100,rel=1e-6)


def test_double_feet_keep_uncovered_gap_and_no_hull():
    model=assembly()
    r=generate(params(model),model,'r1')
    frame=r['drawing_document']['frame']
    pt=Point(30-frame['origin'][0],15-frame['origin'][1])
    assert not any(Polygon(a['loops'][0]['points']).covers(pt) for a in r['regions'])


def test_single_connected_mounting_part_keeps_two_actual_feet():
    feet=box(10,10,.099,10,10,8).fuse(box(40,10,.099,10,10,8),box(10,10,8,40,10,4)).clean()
    m=from_shapes([box(0,0,-5,100,80,5),feet]);r=generate(params(m),m,'r')
    assert r['status']=='passed' and len(r['regions'])==2
    assert all(x['area_mm2']==pytest.approx(220+9*math.pi,rel=1e-6) for x in r['regions'])


@pytest.mark.parametrize('x,count',[(26,2),(25.9,1),(24,1),(40,2)])
def test_only_positive_overlap_merges_and_retains_many_to_many_sources(x,count):
    model=assembly(second_x=x)
    r=generate(params(model),model,'r1')
    assert r['status']=='passed',r['diagnostics']
    assert len(r['regions'])==count
    if count==1:
        assert {s['instance_id'] for s in r['regions'][0]['source_refs']}=={'occ-0','occ-1','occ-2'}
        assert len(r['regions'][0]['provenance'])==2


def test_side_neighbor_not_projected():
    m=from_shapes([box(0,0,-5,100,80,5),box(100.05,10,-4,5,10,3)])
    r=generate(params(m),m,'r')
    assert r['status']=='passed' and not r['regions']


def test_component_outside_target_plane_slab_consumes_no_pair_budget():
    m=from_shapes([box(0,0,-5,100,80,5),box(10,10,100,10,10,8)])
    r=generate(params(m),m,'r',budget=Budget(maximum_pairs=1))
    assert r['status']=='passed' and not r['regions']


def test_tangent_shell_source_generates_reviewable_protection():
    source_box=box(10,10,.05,10,10,2)
    source_face=min(source_box.Faces(),key=lambda face:face.Center().z)
    m=from_shapes([box(0,0,-5,100,80,5),source_face])
    r=generate(params(m),m,'shell-contact')
    assert r['status']=='needs_review' and r['drawing_document'] is not None
    assert len(r['regions'])==1 and r['regions'][0]['kind']=='contact'
    assert any(d['code']=='shell_contact_source' for d in r['diagnostics'])


def test_shell_crossing_target_plane_requires_review_but_keeps_drawing():
    crossing=next(face for face in box(10,10,-1,10,2,2).Faces()
                  if face.BoundingBox().zlen>1.9 and face.BoundingBox().xlen>9)
    m=from_shapes([box(0,0,-5,100,80,5),crossing])
    r=generate(params(m),m,'shell-crossing')
    assert r['status']=='needs_review' and r['drawing_document'] is not None
    diagnostic=next(d for d in r['diagnostics'] if d['code']=='plane_section_open')
    assert diagnostic['source_refs']==[params(m)['target_face_refs'][0],m.occurrences[1].refs[0]]
    assert diagnostic['observed']['gap_bounds_mm']==pytest.approx([-1,1])


def test_composite_shell_ignores_remote_crossing_face_and_keeps_contact():
    contact_box=box(10,10,.05,10,10,2)
    contact=min(contact_box.Faces(),key=lambda face:face.Center().z)
    remote=next(face for face in box(200,200,-10,10,2,20).Faces()
                if face.BoundingBox().zlen>19 and face.BoundingBox().xlen>9)
    shell=cq.Compound.makeCompound([contact,remote])
    m=from_shapes([box(0,0,-5,100,80,5),shell])
    r=generate(params(m),m,'composite-shell')
    assert r['status']=='needs_review' and r['drawing_document'] is not None
    assert len(r['regions'])==1 and r['regions'][0]['kind']=='contact'


def test_tiny_tilt_does_not_use_centroid_gap_as_uniform_contact():
    foot=box(10,10,.099,10,10,8).rotate((10,10,.099),(11,10,.099),.0001)
    m=from_shapes([box(0,0,-5,100,80,5),foot]);r=generate(params(m),m,'r')
    assert r['status']=='needs_review' and not r['regions']
    assert any(d['code']=='nonparallel_gap_unknown' for d in r['diagnostics'])


def test_penetration_produces_target_plane_footprints_with_contact_offset():
    m=assembly(-.2)
    r=generate(params(m),m,'r')
    assert r['status']=='passed' and r['drawing_document'] is not None
    assert len(r['regions'])==2
    assert all(region['area_mm2']==pytest.approx(100+40*3+math.pi*9,rel=1e-6) for region in r['regions'])
    assert all(region['provenance'][0]['evidence']['method']=='target_plane_section' for region in r['regions'])


def test_multiple_crossing_contours_merge_after_common_three_mm_offset():
    crossing=cq.Compound.makeCompound([
        box(10,10,-1,10,10,2),
        box(24,10,-1,10,10,2),
    ])
    m=from_shapes([box(0,0,-5,100,80,5),crossing])
    r=generate(params(m),m,'merged-sections')
    assert r['status']=='passed' and len(r['regions'])==1
    assert r['regions'][0]['kind']=='contact'
    assert r['regions'][0]['contributor_kinds']==['contact']


def test_hollow_crossing_section_retains_unprotected_void():
    crossing=box(10,10,-1,30,30,2).cut(box(18,18,-2,14,14,4))
    m=from_shapes([box(0,0,-5,100,80,5),crossing])
    r=generate(params(m),m,'hollow-section')
    assert r['status']=='passed' and len(r['regions'])==1
    assert len(r['regions'][0]['loops'])==2
    frame=r['drawing_document']['frame']
    center=Point(25-frame['origin'][0],25-frame['origin'][1])
    outer=Polygon(r['regions'][0]['loops'][0]['points'],
                  [loop['points'] for loop in r['regions'][0]['loops'][1:]])
    assert not outer.covers(center)


def test_invalid_plane_section_keeps_reviewable_outline(monkeypatch):
    import thermal_drawings.paint.contacts as contacts
    monkeypatch.setattr(contacts,'target_plane_patches',lambda *args:(None,'Injected section failure'))
    m=assembly(-.2);r=generate(params(m),m,'invalid-section')
    assert r['status']=='needs_review' and r['drawing_document'] is not None
    assert not r['regions']
    assert any(d['code']=='plane_section_invalid' for d in r['diagnostics'])


def test_same_direction_face_excluded_and_custom_threshold():
    m=assembly(.15);p=params(m);p['contact_threshold_mm']=.2
    r=generate(p,m,'r')
    assert len(r['regions'])==2
    assert any(e.get('decision')=='direction_excluded' for e in r['evidence'])


def test_occurrence_positions_rotation_and_source_immutable(tmp_path):
    transform=lambda s:s.rotate((0,0,0),(1,0,0),32).translate((200,30,10))
    m=assembly(transform=transform)
    face=next(r for o,f,r in m.faces if o is m.occurrences[0] and f.geomType()=='PLANE' and f.normalAt().z>.8 and f.Area()>7000)
    before=[]
    for i,o in enumerate(m.occurrences):
        f=tmp_path/f'{i}.brep';o.shape.exportBrep(str(f));before.append(f.read_bytes())
    r=generate(params(m,face),m,'rotated')
    assert r['status']=='passed' and len(r['regions'])==2
    for i,o in enumerate(m.occurrences):
        f=tmp_path/f'{i}.brep';o.shape.exportBrep(str(f));assert before[i]==f.read_bytes()
    for region,overlay in zip(r['regions'],r['overlay']):
        uv=region['loops'][0]['points'][0];frame=region['local_frame']
        expected=[frame['origin'][i]+uv[0]*frame['x_axis'][i]+uv[1]*frame['y_axis'][i] for i in range(3)]
        assert overlay['loops_world_mm'][0][0]==pytest.approx(expected,abs=1e-6)
