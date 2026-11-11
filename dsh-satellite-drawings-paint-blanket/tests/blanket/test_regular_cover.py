import copy
import math
import pytest
import cadquery as cq
from thermal_drawings.blanket.pipeline import generate
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.selection import Frame, BlanketError
from thermal_drawings.blanket.panels import domain
from thermal_drawings.paint.selection import Model
from helpers import fixture, model_for, check


def regular(shape=None, policy='regular_box_v1', extra=(), frame=None):
    p,m=fixture(shape=shape,frame=frame)
    p.update(envelope_policy=policy,piece_limit=10,layer_count=1,volume_ratio_reference=1.2,
             opening_options=dict(shape='circle',padding_mm=0,size_scale=1))
    all_occ=list(m.occurrences)
    for name,s in extra:
        all_occ.extend(model_for(Frame(p['installation_frame']).world(s),name).occurrences)
    m=Model(m.model_ref,all_occ)
    local=Frame(p['installation_frame'])
    p['installation_face']=next(r for o in m.occurrences if o.id=='equipment' for r in o.refs
                                if r['signature']['type']=='PLANE' and abs(local.local(m.resolve(r)[1]).Center().z)<1e-6)
    return p,m


def test_multi_instance_regular_box_and_linear_allowance_bottom_fixed():
    p,m=regular(extra=[('other',cq.Solid.makeBox(20,20,20,cq.Vector(60,-10,0)))])
    p['target_instances'].append('other')
    r=generate(p,m,'r1')
    assert r['status']=='passed'
    assert r['dimensions_mm']==pytest.approx([136.5,105,105])
    assert r['regular_envelope']['bottom_fixed']
    assert check(r,'coverage')['status']=='pass'
    n=generate_net(r)
    assert n['manufacturing_summary']['pieces_per_layer']==len(n['pieces'])==1


def test_rotated_frame_and_disconnected_selected_object():
    frame=dict(origin=[30.,40.,50.],x_axis=[0.,1.,0.],y_axis=[0.,0.,1.],z_axis=[1.,0.,0.],units='mm',handedness='right')
    p,m=regular(frame=frame,extra=[('other',cq.Solid.makeBox(5,10,15,cq.Vector(70,0,20)))])
    p['target_instances'].append('other')
    r=generate(p,m,'rotated')
    assert check(r,'coverage')['status']=='pass'
    assert generate_net(r)['foldback']['status']=='pass'


def test_top_excluded_cylinder_creates_same_3d_2d_opening(tmp_path):
    boss=cq.Solid.makeCylinder(8,30,cq.Vector(0,0,95))
    p,m=regular(extra=[('boss',boss)])
    p['target_instances'].append('boss');p['excluded_instances']=['boss']
    r=generate(p,m,'opening',tmp_path)
    assert r['dimensions_mm']==pytest.approx([105,105,105])
    top=next(panel for panel in r['panels'] if panel['key']=='z+')
    assert len(top['holes'])==1
    assert r['regular_envelope']['openings'][0]['panel']=='z+'
    native=cq.Shape.importBrep(str(tmp_path/top['surface_ref']))
    assert native.Area()==pytest.approx(domain(top).area,abs=1e-6)
    n=generate_net(r,output=tmp_path)
    nt=next(panel for panel in n['panels'] if panel['key']=='z+')
    assert len(nt['net_holes'])==1 and len(nt['net_holes'][0])==128
    assert n['native_readback']['flat-body.brep']['valid']
    assert n['foldback']['status']=='pass'


def test_cylinder_preserves_native_side_and_two_cutting_pieces(tmp_path):
    p,m=regular(cq.Solid.makeCylinder(30,80),policy='regular_cylinder_v1')
    p['layer_count']=3;p['piece_limit']=2
    r=generate(p,m,'cylinder',tmp_path)
    assert r['dimensions_mm']==pytest.approx([63,63,84],abs=1e-5)
    side=next(panel for panel in r['panels'] if panel['key']=='cylinder-side')
    native=cq.Shape.importBrep(str(tmp_path/side['surface_ref']))
    assert native.Faces()[0].geomType()=='CYLINDER'
    n=generate_net(r,output=tmp_path)
    assert n['status']=='passed'
    assert len(n['overlaps'])==1 and n['overlaps'][0]['width_mm']==15
    seam=next(s for s in n['seams'] if s['kind']=='join')
    edited=generate_net(r,dict(seam_overrides=[dict(id=seam['id'],kind='join',overlap_owner_panel=seam['overlap_owner_panel'],width_mm=7)]))
    assert edited['status']=='passed' and edited['overlaps'][0]['width_mm']==7
    assert n['manufacturing_summary']==dict(pieces_per_layer=2,layer_count=3,total_pieces=6,piece_limit=2,limit_reached=True,requirements_unmet=[],count_basis='final_cut_pieces')
    assert 'CYLINDER' in n['native_readback']['folded-body.brep']['surface_types']


def test_cylinder_top_opening_and_cross_face_rejection():
    p,m=regular(cq.Solid.makeCylinder(30,80),policy='regular_cylinder_v1',extra=[('boss',cq.Solid.makeCylinder(5,20,cq.Vector(0,0,75)))])
    p['excluded_instances']=['boss']
    r=generate(p,m,'cylinder-hole')
    assert len(next(panel for panel in r['panels'] if panel['key']=='z+')['holes'])==1
    p,m=regular(extra=[('corner',cq.Solid.makeBox(20,20,30,cq.Vector(45,45,95)))])
    p['excluded_instances']=['corner']
    with pytest.raises(BlanketError,match='multiple_cover_faces'):
        generate(p,m,'cross')


def test_hard_final_piece_limit_and_soft_volume_reference():
    p,m=regular(cq.Solid.makeCylinder(30,80),policy='regular_cylinder_v1')
    p['piece_limit']=1
    r=generate(p,m,'limit')
    assert r['status']=='failed' and r['manufacturing_summary']['requirements_unmet']==['piece_limit_exceeded']
    with pytest.raises(BlanketError,match='piece_limit_exceeded'):generate_net(r)
    p,m=regular();p['allowance']['factors']=[1.2]*3
    r=generate(p,m,'volume')
    assert r['regular_envelope']['volume_reference_exceeded']
    assert check(r,'volume_ratio')['status']=='pass' and generate_net(r)['status']=='passed'
    # Explicitly separating all five faces creates five independent final pieces.
    r=generate(p,m,'separate')
    r['parameters']['piece_limit']=2
    from thermal_drawings.blanket.seams import adjacency
    _,seams=adjacency(r['panels'])
    with pytest.raises(BlanketError,match='piece_limit_exceeded'):
        generate_net(r,dict(fold_seam_ids=[],cut_seam_ids=[s['id'] for s in seams]))


def test_scope_rejections_and_server_parameter_validation():
    p,m=regular(cq.Solid.makeCylinder(30,80),policy='regular_cylinder_v1',extra=[('side',cq.Solid.makeBox(20,10,10,cq.Vector(25,-5,30)))])
    p['excluded_instances']=['side']
    with pytest.raises(BlanketError,match='cylinder_side_unsupported'):generate(p,m,'side')
    p,m=regular();p['piece_limit']=0
    with pytest.raises(Exception):generate(p,m,'invalid')
    p,m=regular();p['installation_face']=next(r for r in m.occurrences[0].refs if r['signature']['centroid_mm'][2]>99)
    with pytest.raises(BlanketError,match='match_selected_plane'):generate(p,m,'wrong-plane')


def test_target_volume_union_deduplicates_overlap_and_excludes_uncovered_parts():
    p,m=regular(extra=[('overlap',cq.Solid.makeBox(100,100,100,cq.Vector(0,-50,0))),
                       ('excluded',cq.Solid.makeCylinder(8,30,cq.Vector(0,0,95)))])
    p['target_instances'] += ['overlap','excluded'];p['excluded_instances']=['excluded']
    r=generate(p,m,'volume-union')['regular_envelope']
    assert r['target_volume_mm3']==pytest.approx(1500000,abs=1e-5)
    assert r['target_volume_measurement']['status']=='measured'
    assert r['target_volume_measurement']['overlaps']=='counted_once_by_union'
    assert r['envelope_to_target_volume_ratio']==pytest.approx(r['envelope_volume_mm3']/1500000)
    assert r['volume_ratio_metric']=='allowance_envelope_volume_ratio'


def test_target_volume_preserves_cavities_and_measures_loose_regular_cover():
    outer=cq.Solid.makeBox(100,100,100,cq.Vector(-50,-50,0))
    inner=cq.Solid.makeBox(80,80,80,cq.Vector(-40,-40,10))
    p,m=regular(outer.cut(inner))
    r=generate(p,m,'hollow')['regular_envelope']
    assert r['target_volume_mm3']==pytest.approx(1000000-512000,abs=1e-5)
    assert r['volume_ratio']==pytest.approx(1.05**3)
    assert r['envelope_to_target_volume_ratio']>2
    assert r['target_volume_measurement']['cavities']=='excluded_from_net_volume'


def test_target_volume_unavailable_is_explicit_not_a_sum(monkeypatch):
    import thermal_drawings.blanket.regular_cover as regular_module
    original=regular_module.boolean
    def union_failure(kind,left,right):
        if kind==regular_module.BRepAlgoAPI_Fuse:raise RuntimeError('kernel cannot measure this union')
        return original(kind,left,right)
    monkeypatch.setattr(regular_module,'boolean',union_failure)
    p,m=regular(extra=[('other',cq.Solid.makeBox(20,20,20,cq.Vector(60,-10,0)))])
    p['target_instances'].append('other')
    r=generate(p,m,'unavailable')
    assert r['status']=='passed'
    assert r['regular_envelope']['target_volume_mm3'] is None
    assert r['regular_envelope']['envelope_to_target_volume_ratio'] is None
    assert r['regular_envelope']['target_volume_measurement']['reason']=='native_union_measurement_failed'


def test_cylinder_drawing_uses_one_diameter_and_readable_strip_dimensions(tmp_path):
    p,m=regular(cq.Solid.makeCylinder(40,100),policy='regular_cylinder_v1',
                extra=[('boss',cq.Solid.makeCylinder(5,20,cq.Vector(0,0,95)))])
    p['excluded_instances']=['boss']
    cover=generate(p,m,'readable-cylinder')
    net=generate_net(cover)
    assert len(net['pieces'])==2 and net['status']=='passed'
    dimensions=[e for e in net['drawing_document']['entities'] if e['kind']=='dimension']
    lengths=[math.dist(e['start'],e['end']) for e in dimensions]
    assert len(dimensions)==3
    assert sorted(lengths)==pytest.approx(sorted([84,105,84*math.pi]),abs=1e-5)
    # The top aperture and all outer cuts remain complete. Drawing replacement
    # only changes annotations, never sampled manufacturing material.
    from thermal_drawings.blanket.material import cut_boundary_check
    assert cut_boundary_check(net,net['drawing_document'])['missing_cut_length_mm']<1e-6
    top=next(panel for panel in net['panels'] if panel['key']=='z+')
    assert len(top['net_holes'])==1 and len(top['net_holes'][0])==128
    from thermal_drawings.blanket.net_drawing import drawing
    point=[*top['net_outer'][0]]
    net['fixed_points']=[dict(id='point',status='valid',panel_key='z+',net_uv_mm=point)]
    doc=drawing(net)
    assert len([e for e in doc['entities'] if e['kind']=='point' and e['layer']=='FIXING'])==1
    # Verify actual editable output entities as well as the drawing document.
    import ezdxf
    from thermal_drawings.drawing.document import DrawingDocument
    from thermal_drawings.drawing.dxf_export import DrawingExporter
    dxf=DrawingExporter().write_dxf(DrawingDocument(doc),tmp_path/'readable-cylinder.dxf')
    space=ezdxf.readfile(dxf).modelspace()
    actual=list(space.query('DIMENSION'))
    assert len(actual)==3
    assert sorted(e.get_measurement() for e in actual)==pytest.approx(sorted([84,105,84*math.pi]),abs=1e-5)
    assert len(space.query('POINT'))==1


def test_dimension_simplification_requires_regular_cylinder_and_exact_sampled_circle():
    from thermal_drawings.blanket.net_drawing import drawing
    p,m=regular(cq.Solid.makeCylinder(40,100),policy='regular_cylinder_v1')
    net=generate_net(generate(p,m,'scope-cylinder'))
    legacy=copy.deepcopy(net);legacy.pop('regular_envelope')
    assert len([e for e in drawing(legacy)['entities'] if e['kind']=='dimension'])==130
    # Equal metadata alone cannot suppress a noncircular/complex face's sizes.
    top=next(panel for panel in net['panels'] if panel['key']=='z+')
    top['outer_loop']['points'][0][0]+=.1
    from thermal_drawings.blanket.net_drawing import _regular_circular_top
    assert _regular_circular_top(net,top) is None


def test_installation_plane_must_belong_to_included_target():
    p,m=regular(extra=[('other',cq.Solid.makeBox(10,10,10,cq.Vector(200,200,0)))])
    p['installation_face']=next(ref for o in m.occurrences if o.id=='other' for ref in o.refs
                                if abs(m.resolve(ref)[1].Center().z)<1e-6)
    with pytest.raises(BlanketError,match='must_belong_to_selected_target'):
        generate(p,m,'unrelated-plane')
    p['target_instances'].append('other');p['excluded_instances']=['other']
    with pytest.raises(BlanketError,match='must_belong_to_selected_target'):
        generate(p,m,'excluded-plane')


def test_excluded_geometry_is_budgeted_before_copy_or_native_operations():
    from thermal_drawings.paint.selection import Occurrence
    class OversizedExcluded:
        def Faces(self):return range(20001)
        def copy(self):raise AssertionError('oversized geometry must be rejected before copying')
    p,m=regular()
    m.occurrences.append(Occurrence('huge',OversizedExcluded(),[]))
    p['excluded_instances']=['huge']
    with pytest.raises(BlanketError,match='regular_cover_geometry_budget'):
        generate(p,m,'oversized-exclusion')


def test_cover_count_matches_primary_connected_plan_and_preserves_over_limit_preview():
    from thermal_drawings.runtime.publication import reviewable_limit_preview
    p,m=regular();p['piece_limit']=2
    cover=generate(p,m,'primary-plan')
    assert cover['manufacturing_summary']['pieces_per_layer']==4
    assert cover['regular_envelope']['piece_count_plan']=='connected_15mm_v1'
    assert cover['status']=='failed' and reviewable_limit_preview(cover)
    from thermal_drawings.domain.acceptance import usable
    assert not usable(cover)
    damaged=copy.deepcopy(cover)
    next(c for c in damaged['checks'] if c['id']=='coverage')['status']='fail'
    assert not reviewable_limit_preview(damaged)
    damaged=copy.deepcopy(cover);damaged['parameters']['envelope_policy']='installation_box'
    assert not reviewable_limit_preview(damaged)


def test_cylinder_envelope_does_not_mistake_fused_box_boss_for_pure_cylinder():
    shape=cq.Solid.makeBox(100,100,80,cq.Vector(-50,-50,0)).fuse(cq.Solid.makeCylinder(15,30,cq.Vector(0,0,75)))
    p,m=regular(shape,policy='regular_cylinder_v1')
    cover=generate(p,m,'combined-single-solid')
    assert check(cover,'coverage')['status']=='pass'
    assert cover['regular_envelope']['diameter_mm']==pytest.approx(math.sqrt(2)*100*1.05,abs=1e-5)


def test_http_over_limit_cover_is_visible_but_net_export_and_bundle_are_blocked(tmp_path):
    import json
    from pathlib import Path
    from workflow import Service,current,result,ROOT
    service=Service(tmp_path/'limit-preview-http')
    # Enable the export route while retaining a deliberately unusable test
    # converter: over-limit requests must fail before any conversion is queued.
    service.stop()
    converter=tmp_path/'disabled-converter.json'
    converter.write_text(json.dumps({'dwg':{'adapter':'not-used-in-rejection-test'}}))
    config=json.loads(service.config.read_text());config['converter_config']=str(converter)
    service.config.write_text(json.dumps(config));service.start()
    try:
        for fixture_name,policy,limit,expected_count in [('cylinder','regular_cylinder_v1',1,2),('cube','regular_box_v1',2,4)]:
            project=service.project('blanket')
            path=ROOT/f'fixtures/synthetic/simple-v1/{fixture_name}.step'
            asset=service.call('POST',f'/projects/{project}/assets',path.read_bytes(),who='blanket',expected=201,
                               headers={'Content-Type':'application/step','X-Filename':path.name})[1]
            imported=service.wait(service.submit_import(project,asset,who='blanket'),'blanket')
            assert imported['state']=='succeeded',imported
            revision=current(service,project)
            model=service.call('GET',f"/projects/{project}/models/{revision['model_ref']['model_id']}",who='blanket')[1]
            asset=next(a for a in model['artifacts'] if a['relative_storage_path'].endswith('mesh-map.json'))
            mapping=service.call('GET','/artifacts/'+asset['id'],who='blanket')[1]
            refs=[f['face_ref'] for f in mapping['faces']]
            parameters=json.loads((ROOT/'fixtures/contracts/blanket.json').read_text())
            parameters.update(model_ref=revision['model_ref'],target_instances=sorted({r['instance_id'] for r in refs}),
                              installation_face=next(r for r in refs if r['signature']['type']=='PLANE' and abs(r['signature']['centroid_mm'][2])<1e-6),
                              envelope_policy=policy,piece_limit=limit)
            submitted=service.operation(project,revision,'blanket.generate',parameters,who='blanket')
            finished=service.wait(submitted['run_id'],'blanket')
            assert finished['state']=='succeeded',finished
            assert next(c for c in finished['checks'] if c['id']=='publication')['observed']['preview_only'] is True
            assert next(c for c in finished['checks'] if c['id']=='piece_limit')['status']=='fail'
            preview=result(service,project)
            assert preview['blanket']['status']=='failed'
            assert preview['blanket']['manufacturing_summary']['pieces_per_layer']==expected_count
            glb=next(a for a in finished['artifacts'] if a['role']=='blanket_display')
            assert service.call('GET','/artifacts/'+glb['id'],who='blanket',raw=True)[1][:4]==b'glTF'
            assert service.call('GET',f'/projects/{project}/blanket-net',who='blanket')[1] is None
            revision=current(service,project)
            rejected=service.operation(project,revision,'blanket.unfold',dict(result_id=preview['result_id'],settings=dict(connection_plan='connected_15mm_v1')),who='blanket',expected=422)
            assert rejected['code']=='piece_limit_exceeded'
            service.operation(project,revision,'drawing.export',dict(result_id=preview['result_id'],draft=True),who='blanket',expected=409)
            rejected=service.operation(project,revision,'engineering.save',{},who='blanket',expected=422)
            assert rejected['code']=='piece_limit_exceeded'
            assert result(service,project)['result_id']==preview['result_id']
    finally:
        service.close()


def test_connected_cylinder_dxf_dimensions_include_full_height_despite_tab_relief(tmp_path):
    import ezdxf
    from thermal_drawings.drawing.document import DrawingDocument
    from thermal_drawings.drawing.dxf_export import DrawingExporter
    from thermal_drawings.blanket.material import cut_boundary_check
    p,m=regular(cq.Solid.makeCylinder(40,80),policy='regular_cylinder_v1',
                extra=[('boss',cq.Solid.makeCylinder(5,20,cq.Vector(0,0,75)))])
    p['excluded_instances']=['boss']
    cover=generate(p,m,'connected-cylinder-height')
    settings=dict(connection_plan='connected_15mm_v1')
    point_command=dict(action='add',id='height-check-point',panel_key='cylinder-side',uv_mm=[20,20])
    net=generate_net(cover,settings,point_command=point_command)
    assert len(net['pieces'])==2 and net['status']=='passed'
    assert net['settings']['corner_relief_mode']=='native_boundary'
    root=net['overlaps'][0]['uv'][:2]
    assert math.dist(*root)==pytest.approx(54,abs=1e-5)
    assert len(next(panel for panel in net['panels'] if panel['key']=='z+')['net_holes'][0])==128
    assert cut_boundary_check(net,net['drawing_document'])['missing_cut_length_mm']<1e-6
    path=DrawingExporter().write_dxf(DrawingDocument(net['drawing_document']),tmp_path/'connected-full-height.dxf')
    space=ezdxf.readfile(path).modelspace()
    dimensions=list(space.query('DIMENSION'))
    assert len(dimensions)==3
    # Diameter and full side-strip height are both 84; no 54mm tab-root labels.
    assert sorted(e.get_measurement() for e in dimensions)==pytest.approx([84,84,84*math.pi],abs=1e-5)
    assert len(space.query('POINT'))==1
