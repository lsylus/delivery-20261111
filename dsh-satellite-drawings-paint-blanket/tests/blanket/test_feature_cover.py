import copy
import json
import math
from pathlib import Path
import cadquery as cq
import pytest
from shapely.geometry import Point,Polygon
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.net_operations import rebuild_net
from thermal_drawings.blanket.fixed_points import edit,seed_feature_points
from thermal_drawings.blanket.selection import BlanketError,Frame
from thermal_drawings.blanket.panels import domain,NetError
from helpers import model_for,check,ROOT


def parameters(shape,limit=50):
    p=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text());m=model_for(shape)
    p.update(model_ref=m.model_ref,target_instances=['equipment'],envelope_policy='feature_composite_v1',piece_limit=limit)
    from thermal_drawings.blanket.surface_charts import descriptor
    planar=None
    for f,r in zip(shape.Faces(),m.occurrences[0].refs):
        if f.geomType()!='PLANE':continue
        d=descriptor(f);offset=[shape.Center().toTuple()[i]-d['origin'][i] for i in range(3)]
        if sum(offset[i]*d['z_axis'][i] for i in range(3))<0:
            d['y_axis']=[-v for v in d['y_axis']];d['z_axis']=[-v for v in d['z_axis']]
        frame={k:d[k] for k in ('origin','x_axis','y_axis','z_axis')};frame.update(units='mm',handedness='right')
        if Frame(frame).local(shape.copy()).BoundingBox().zmin>=-1e-5:planar=(r,frame);break
    if planar:
        r,frame=planar;p['installation_face']=r
        p['installation_frame']=frame
    return p,m

@pytest.fixture(scope='module')
def motor():
    shape=cq.Shape.importBrep(str(ROOT/'fixtures/real-derived/b13/motor.brep'))
    p,m=parameters(shape)
    return p,m,generate(p,m,'native-motor')


def test_motor_full_native_features_union_exterior_and_cap_preview(motor,tmp_path):
    p,m,c=motor
    assert len(m.occurrences[0].shape.Faces())==44
    f=c['feature_composite'];assert f['primitive_count']==8 and f['manufacturing_panel_count']==len(c['panels'])==23
    assert f['uncovered_source_volume_mm3']==pytest.approx(0,abs=1e-5)
    assert f['internal_surface_policy']=='union_exterior_only'
    assert len([x for x in f['features'] if x['kind']=='box'])==1
    assert sum(x['label'].startswith('Radial') for x in f['features'])==4
    assert check(c,'coverage')['status']=='pass' and check(c,'feature_interfaces')['status']=='needs_review'
    assert {x for i in f['interfaces'] for x in i['panel_keys']}=={p['key'] for p in c['panels']}
    assert f['default_piece_count']==c['manufacturing_summary']['pieces_per_layer']==20
    initial=copy.deepcopy(c);initial['parameters'].pop('piece_limit');initial['manufacturing_summary']['piece_limit']=10
    n=generate_net(initial)
    assert len(n['pieces'])==20 and n['status']=='failed'
    assert n['manufacturing_summary']['requirements_unmet']==['piece_limit_exceeded']
    n=generate_net(c)
    assert n['status']=='needs_review' and not n['diagnostics'] and n['foldback']['maximum_error_mm']<1e-6
    assert len([s for s in n['seams'] if s['kind']=='fold'])==3
    fan_tabs=[t for t in n['overlaps'] if t.get('surface_width_measurement',{}).get('pattern')=='segmented_fan_tabs_v1']
    assert fan_tabs and all(t['width_mm']==15 and t['surface_width_measurement']['acceptance']=='needs_material_sample' for t in fan_tabs)
    assert all(i['overlap_status']=='generated_needs_material_sample' for i in n['feature_composite']['interfaces'] if i['native_curve_types']==['CIRCLE'])
    assert 6<=len(n['fixed_points'])<=12
    for point in n['fixed_points']:
        panel=next(p for p in n['panels'] if p['key']==point['panel_key']);q=Point(point['uv_mm'])
        assert point['status']=='valid' and domain(panel).boundary.distance(q)>=8-1e-7
        for tab in n['overlaps']:
            if tab['target_panel']==point['panel_key']:assert not Polygon(tab['receiving_uv']).buffer(8-1e-7).contains(q)
    assert len([e for e in n['drawing_document']['entities'] if e['kind']=='point' and e['layer']=='FIXING'])==len(n['fixed_points'])


def test_motor_rigid_placement_keeps_features_and_containment(motor):
    p,m,c=motor
    transformed=m.occurrences[0].shape.rotate((0,0,0),(1,2,3),57).translate((213,-65,91))
    pp,mm=parameters(transformed);other=generate(pp,mm,'rigid-motor')
    assert other['feature_composite']['primitive_count']==8
    assert other['feature_composite']['uncovered_source_volume_mm3']<1e-5
    assert other['baseline']['volume_mm3']==pytest.approx(c['baseline']['volume_mm3'],rel=1e-5)
    assert sum(p['surface_trim']['native_area_mm2'] for p in other['panels'])==pytest.approx(sum(p['surface_trim']['native_area_mm2'] for p in c['panels']),rel=1e-4)


def test_native_artifacts_and_editable_dxf_marker_readback(motor,tmp_path):
    p,m,_=motor;c=generate(p,m,'native-readback',tmp_path);n=generate_net(c,output=tmp_path)
    assert n['native_readback']['flat-body.brep']['valid']
    assert 'CYLINDER' in n['native_readback']['folded-body.brep']['surface_types']
    actual=cq.Shape.importBrep(str(tmp_path/'evaluation.brep'))
    assert len(actual.Faces())==len(c['panels'])+1
    manufacturing=Frame(p['installation_frame']).local(cq.Shape.importBrep(str(tmp_path/'manufacturing.brep')))
    assert min(v.Center().z for v in manufacturing.Vertices())>=-1e-5
    assert not any(f.geomType()=='PLANE' and max(abs(f.BoundingBox().zmin),abs(f.BoundingBox().zmax))<1e-5 for f in manufacturing.Faces())
    cap=Frame(p['installation_frame']).local(cq.Shape.importBrep(str(tmp_path/'closures/installation-bottom.brep')))
    assert cap.Faces() and all(max(abs(f.BoundingBox().zmin),abs(f.BoundingBox().zmax))<1e-5 for f in cap.Faces())
    # Position markers do not change BRep area or create holes.
    assert len(cq.Shape.importBrep(str(tmp_path/'folded-body.brep')).Faces())==23
    import ezdxf
    from thermal_drawings.drawing.document import DrawingDocument
    from thermal_drawings.drawing.dxf_export import DrawingExporter
    path=DrawingExporter().write_dxf(DrawingDocument(n['drawing_document']),tmp_path/'native-feature.dxf')
    points=list(ezdxf.readfile(path).modelspace().query('POINT'))
    assert len(points)==len(n['fixed_points']) and all(e.dxf.layer=='FIXING' for e in points)


def test_auto_points_deterministic_replay_move_delete_and_initial_restore(motor):
    _,_,cover=motor
    initial=rebuild_net(cover,dict(document_edits=[]),None)
    old=copy.deepcopy(initial['fixed_points']);again=rebuild_net(dict(cover,revision_id='restored-initial'),dict(document_edits=[]),None)
    assert len({p['panel_key'] for p in old})==len(old)
    assert [(p['id'],p['uv_mm']) for p in old]==[(p['id'],p['uv_mm']) for p in again['fixed_points']]
    point=old[0];state=copy.deepcopy(initial['point_state'])
    moved_uv=[point['uv_mm'][0]+1,point['uv_mm'][1]]
    command=dict(action='move',id=point['id'],panel_key=point['panel_key'],uv_mm=moved_uv)
    revision=dict(document_edits=[dict(kind='blanket_net_v1',settings=initial['settings'],point_state=state,point_command=command)])
    moved=rebuild_net(dict(cover,revision_id='moved'),revision,None)
    replay=rebuild_net(dict(cover,revision_id='restored-move'),revision,None)
    assert moved['fixed_points'][0]['uv_mm']==replay['fixed_points'][0]['uv_mm']==moved_uv
    assert moved['fixed_points'][0]['position3d']==replay['fixed_points'][0]['position3d']
    for point in old:state=edit(initial,state,dict(action='delete',id=point['id']))
    assert not state['points'] and state['used_ids']
    revision['document_edits'][0].update(point_state=state,point_command=None)
    deleted=rebuild_net(dict(cover,revision_id='deleted'),revision,None)
    restored=rebuild_net(dict(cover,revision_id='restored-deleted'),revision,None)
    assert not deleted['fixed_points'] and not restored['fixed_points']
    before=copy.deepcopy(moved['point_state'])
    with pytest.raises(NetError):edit(moved,before,dict(action='move',id=old[0]['id'],panel_key=old[0]['panel_key'],uv_mm=[1e7,1e7]))
    assert before==moved['point_state']
    # Foreign history reservations must not suppress initial suggestions.
    reserved=dict(points=[],used_ids=['fp:foreign','fp:auto:foreign:initialized'])
    seeded=seed_feature_points(initial,reserved,cover['baseline']['id'])
    assert [p['id'] for p in seeded['points']]==[p['id'] for p in old]


def test_plain_box_and_box_cylinder_leaves_derived_from_native_geometry():
    from thermal_drawings.paint.selection import Model
    box=cq.Solid.makeBox(100,80,60).rotate((0,0,0),(1,2,1),33).translate((12,23,34))
    p,m=parameters(box);c=generate(p,m,'box')
    assert c['feature_composite']['primitive_count']==1 and len(c['panels'])==5
    box_net=generate_net(c)
    assert len(box_net['pieces'])==1 and len(box_net['pieces'][0]['panel_keys'])==5
    assert len([s for s in box_net['seams'] if s['kind']=='fold'])==4
    assert check(c,'feature_interfaces')['status']=='pass'
    cylinder=cq.Solid.makeCylinder(15,40,cq.Vector(130,20,30))
    other=model_for(cylinder,'cylinder');m=Model(m.model_ref,[*m.occurrences,*other.occurrences]);p['target_instances'].append('cylinder')
    c=generate(p,m,'box-cylinder')
    assert c['feature_composite']['primitive_count']==2 and check(c,'coverage')['status']=='pass'
    n=generate_net(c)
    assert len(n['pieces'])==4 and sorted(len(piece['panel_keys']) for piece in n['pieces'])==[1,1,1,5]
    assert any(t.get('surface_width_measurement',{}).get('pattern')=='segmented_fan_tabs_v1' for t in n['overlaps'])


def test_unrecognized_geometry_is_not_silently_omitted():
    shape=cq.Solid.makeSphere(20);p,m=parameters(shape)
    with pytest.raises(BlanketError,match='installation_face|recognition'):generate(p,m,'sphere')
    cylinder=cq.Solid.makeCylinder(20,100)
    # A sphere boss cannot be mistaken for another external cylinder.
    shape=cylinder.fuse(cq.Solid.makeSphere(15,cq.Vector(25,0,50)));p,m=parameters(shape)
    with pytest.raises(BlanketError,match='unrecognized_source_geometry'):generate(p,m,'unknown-boss')


def test_installation_reference_is_validated_and_closed_exterior_is_explicit(motor):
    p,m,c=motor
    assert c['feature_composite']['installation_opening'] is True
    assert c['feature_composite']['installation_surface_policy']=='selected_installation_plane_clipped_from_manufacturing'
    assert c['closures']==[dict(id='installation-bottom',shape_ref='closures/installation-bottom.brep',evaluation_only=True)]
    assert c['feature_composite']['bottom_fixed'] is False
    bad=copy.deepcopy(p);bad['installation_frame']['origin']=[v+3 for v in bad['installation_frame']['origin']]
    with pytest.raises(BlanketError,match='match_selected_plane'):generate(bad,m,'bad-frame')
    bad=copy.deepcopy(p);bad['installation_face']=next(r for r in m.occurrences[0].refs if r['signature']['type']=='CYLINDER')
    with pytest.raises(BlanketError,match='requires_plane'):generate(bad,m,'curve-support')


def test_excluded_leaf_planar_opening_matches_native_and_flat_domains(tmp_path):
    from thermal_drawings.paint.selection import Model
    body=cq.Solid.makeBox(100,100,100,cq.Vector(-50,-50,0))
    p,m=parameters(body);boss=cq.Solid.makeCylinder(8,40,cq.Vector(0,0,90))
    m=Model(m.model_ref,[*m.occurrences,*model_for(boss,'excluded').occurrences])
    p.update(target_instances=['equipment','excluded'],excluded_instances=['excluded'],opening_options=dict(shape='circle',padding_mm=1,size_scale=1))
    c=generate(p,m,'excluded-planar',tmp_path)
    assert c['feature_composite']['primitive_count']==1
    assert c['feature_composite']['excluded_instances']==['excluded']
    assert c['feature_composite']['openings'][0]['status']=='created'
    panel=next(panel for panel in c['panels'] if panel['holes'])
    assert len(panel['holes'])==1
    native=cq.Shape.importBrep(str(tmp_path/panel['surface_ref']))
    assert native.Area()==pytest.approx(domain(panel).area,abs=1e-5)
    n=generate_net(c,output=tmp_path)
    assert n['areas']['openings_mm2']>math.pi*8**2
    assert n['foldback']['status']=='pass' and not n['diagnostics']
    # No initial suggested marker may enter the actual new aperture.
    for point in n['fixed_points']:
        panel=next(p for p in n['panels'] if p['key']==point['panel_key'])
        assert domain(panel).contains(Point(point['uv_mm']))


def test_excluded_leaf_curve_and_cross_face_openings_are_explicitly_rejected():
    from thermal_drawings.paint.selection import Model
    for body,boss,code in [
        (cq.Solid.makeCylinder(30,100),cq.Solid.makeBox(20,10,10,cq.Vector(25,-5,30)),'curved_surface_unsupported'),
        (cq.Solid.makeBox(100,100,100,cq.Vector(-50,-50,0)),cq.Solid.makeBox(20,20,30,cq.Vector(45,45,95)),'multiple_cover_faces')]:
        p,m=parameters(body);m=Model(m.model_ref,[*m.occurrences,*model_for(boss,'excluded').occurrences]);p['excluded_instances']=['excluded']
        with pytest.raises(BlanketError,match=code):generate(p,m,'unsupported-aperture')
