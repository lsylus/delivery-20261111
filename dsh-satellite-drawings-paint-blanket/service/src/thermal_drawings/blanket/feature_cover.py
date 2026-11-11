"""Native analytic feature envelopes; only the exterior of their union is cut.

Recognition uses native cylinder orientation, coaxiality and shared planar axial
bands. Unsupported shapes fail coverage instead of silently dropping features.
"""
import copy
import json
import math
import time
import numpy as np
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.gp import gp_Trsf
from OCP.TopLoc import TopLoc_Location
from .selection import BlanketError, Frame, shape_hash
from .checks import boolean, record
from .surface_charts import partition
from .regular_cover import summary
from ..domain.validation import canonical, fingerprint, validate

ALGORITHM = 'feature-composite-v1'
POLICY = 'feature_composite_v1'
EPS = 1e-5

def _vec(p): return np.array([p.X(), p.Y(), p.Z()], dtype=float)
def _unit(p): return p / np.linalg.norm(p)
def _line_distance(p, q, d): return float(np.linalg.norm(np.cross(p-q, d)))
def _interval(row, d):
    v=np.array(row['ends'])@d
    return float(v.min()), float(v.max())

def recognize(shape):
    """Return primitive parameters derived only from the supplied native BRep."""
    if len(shape.Solids())>1:
        result=[];all_faces=shape.Faces()
        for solid in shape.Solids():
            indices=[next(i for i,f in enumerate(all_faces) if f.isSame(sf)) for sf in solid.Faces()]
            for p in recognize(solid):
                p['support']=[indices[i] for i in p['support']];result.append(p)
        return result
    faces=shape.Faces(); rows=[]
    for i, f in enumerate(faces):
        a=BRepAdaptor_Surface(f.wrapped); kind=f.geomType()
        r=dict(index=i, kind=kind, area=f.Area())
        if kind=='CYLINDER':
            c=a.Cylinder();d=_vec(c.Axis().Direction());p=_vec(c.Location());u0,u1,v0,v1=f._uvBounds()
            q=_vec(a.Value((u0+u1)/2,(v0+v1)/2)); radial=q-p-d*np.dot(q-p,d)
            r.update(axis=d, origin=p, radius=c.Radius(), ends=[p+d*v0,p+d*v1],
                     full=abs(u1-u0)>=2*math.pi-1e-6,
                     external=np.dot(np.array(f.normalAt(cq.Vector(*q)).toTuple()),radial)>0)
        elif kind=='PLANE':r['normal']=_vec(a.Plane().Axis().Direction())
        rows.append(r)
    external=[r for r in rows if r['kind']=='CYLINDER' and r['full'] and r['external']]
    if not external:
        if len(faces)==6 and all(r['kind']=='PLANE' for r in rows):
            X=rows[0]['normal'];Y=next((r['normal'] for r in rows if abs(np.dot(r['normal'],X))<1e-8),None)
            if Y is not None:
                Z=_unit(np.cross(X,Y));axes=np.column_stack([X,Y,Z])
                if all(max(abs(np.dot(r['normal'],a)) for a in (X,Y,Z))>1-1e-8 for r in rows):
                    pts=np.array([v.toTuple() for v in shape.Vertices()])@axes;lo=pts.min(0);hi=pts.max(0)
                    if abs(float(np.prod(hi-lo))-shape.Volume())<=max(1e-5,shape.Volume()*1e-8):
                        return [dict(kind='box',label='Box body',support=list(range(6)),axes=axes.tolist(),low_mm=lo.tolist(),high_mm=hi.tolist())]
        raise BlanketError('feature_recognition_requires_analytic_box_or_external_full_cylinder')
    body=max(external,key=lambda r:r['area']);X=body['axis'];P=body['origin']
    # Keep native orientation (rather than world-axis sign heuristics) so rigid
    # placements preserve feature order and primitive identity.
    coax=[r for r in external if abs(np.dot(r['axis'],X))>1-1e-8 and _line_distance(r['origin'],P,X)<EPS]
    radial=[r for r in external if abs(np.dot(r['axis'],X))<1e-8]
    groups=[]
    for r in radial:
        d=r['axis'];p=r['origin'];out=p-(P+X*np.dot(p-P,X));d=d if np.dot(d,out)>=0 else -d
        g=next((g for g in groups if np.dot(d,g['axis'])>1-1e-8 and _line_distance(p,g['origin'],d)<EPS),None)
        if g is None:g=dict(axis=d,origin=p,stages=[]);groups.append(g)
        g['stages'].append(r)
    bands={}
    for r,f in zip(rows,faces):
        if r['kind']!='PLANE' or abs(np.dot(r['normal'],X))>1e-7:continue
        points=np.array([v.toTuple() for v in f.Vertices()]);s=points@X
        if s.max()-s.min()<=EPS:continue
        key=tuple(np.round(np.array([s.min(),s.max()])/EPS).astype(int))
        bands.setdefault(key,[]).append(r)
    plate_bands=[]
    for band,rs in bands.items():
        ns=[r['normal'] for r in rs]
        if len(rs)>=4 and any(abs(np.dot(a,b))<1e-7 for a in ns for b in ns):
            plate_bands.append((band,rs))
    parts=[]
    def cylinder(r,label,d):
        lo,hi=_interval(r,d)
        parts.append(dict(kind='cylinder',label=label,support=[r['index']],axis=d.tolist(),
                          origin=r['origin'].tolist(),radius_mm=r['radius'],interval_mm=[lo,hi]))
    cylinder(body,'Main body',X)
    for k,(band,rs) in enumerate(plate_bands):
        band=np.array(band)*EPS;Y=_unit(rs[0]['normal']-X*np.dot(rs[0]['normal'],X));Z=_unit(np.cross(X,Y))
        axes=np.column_stack([X,Y,Z]);members=[];points=[]
        for r,f in zip(rows,faces):
            vs=np.array([v.toTuple() for v in f.Vertices()]);s=vs@X
            if s.min()>=band[0]-EPS and s.max()<=band[1]+EPS:
                members.append(r['index']);points.extend(vs.tolist())
        pts=np.array(points)@axes;lo=pts.min(0);hi=pts.max(0)
        parts.append(dict(kind='box',label='End plate '+str(k+1),support=members,
                          axes=axes.tolist(),low_mm=lo.tolist(),high_mm=hi.tolist()))
    for k,r in enumerate(sorted((r for r in coax if r is not body),key=lambda r:_interval(r,X)[0])):
        cylinder(r,'Axial stage '+str(k+1),X)
    for k,g in enumerate(groups):
        for j,r in enumerate(sorted(g['stages'],key=lambda r:_interval(r,g['axis'])[0])):
            cylinder(r,'Radial '+str(k+1)+' stage '+str(j+1),g['axis'])
    if len(parts)>64:raise BlanketError('feature_primitive_budget')
    return parts

def _primitive(p,factor):
    if p['kind']=='cylinder':
        d=np.array(p['axis']);o=np.array(p['origin']);lo,hi=p['interval_mm'];mid=(lo+hi)/2;half=(hi-lo)*factor/2
        base=o+d*(mid-half-np.dot(o,d))
        return cq.Solid.makeCylinder(p['radius_mm']*factor,2*half,cq.Vector(*base),cq.Vector(*d))
    lo=np.array(p['low_mm']);hi=np.array(p['high_mm']);mid=(lo+hi)/2;dims=(hi-lo)*factor
    axes=np.array(p['axes']);corner=axes@(mid-dims/2);t=gp_Trsf()
    t.SetValues(*[float(v) for row,offset in zip(axes,corner) for v in (*row,offset)])
    return cq.Solid.makeBox(*map(float,dims)).moved(cq.Location(TopLoc_Location(t)))

def _union(shapes):
    # Share the service's serial, non-destructive Boolean policy. CadQuery's
    # fuse enables OCCT's unbounded parallel pool by default, which can stall
    # in worker address-space limits even for these eight simple primitives.
    result=shapes[0]
    for primitive in shapes[1:]:result=boolean(BRepAlgoAPI_Fuse,result,primitive)
    if len(shapes)>1:result=result.clean()
    if not result.isValid() or not result.Solids():raise BlanketError('feature_union_invalid')
    return result

def _clip_to_installation_side(shape,frame):
    local=frame.local(shape.copy());bounds=local.BoundingBox()
    if bounds.zmax<=EPS:raise BlanketError('feature_cover_empty_above_installation_plane')
    margin=max(bounds.xlen,bounds.ylen,bounds.zlen,1.)+1.
    clip=cq.Solid.makeBox(bounds.xlen+2*margin,bounds.ylen+2*margin,bounds.zmax+margin,
                          cq.Vector(bounds.xmin-margin,bounds.ymin-margin,0))
    clipped=boolean(BRepAlgoAPI_Common,local,clip).clean()
    if not clipped.isValid() or not clipped.Solids():raise BlanketError('feature_installation_clip_invalid')
    return frame.world(clipped)

def _installation_caps(shape,frame):
    caps=[]
    for face in shape.Faces():
        local=frame.local(face.copy());bounds=local.BoundingBox()
        if (face.geomType()=='PLANE' and max(abs(bounds.zmin),abs(bounds.zmax))<=10*EPS
                and local.normalAt().z<-.99):caps.append(face)
    if not caps:raise BlanketError('feature_installation_opening_unresolved')
    return caps

def _supported_by(face, primitive):
    """Boolean exterior descendants stay on a primitive analytic support."""
    a=BRepAdaptor_Surface(face.wrapped)
    for pf in primitive.Faces():
        if face.geomType()!=pf.geomType():continue
        b=BRepAdaptor_Surface(pf.wrapped)
        if face.geomType()=='CYLINDER':
            c,d=a.Cylinder(),b.Cylinder();axis=_vec(c.Axis().Direction());other=_vec(d.Axis().Direction())
            if abs(c.Radius()-d.Radius())<EPS and abs(np.dot(axis,other))>1-1e-8 and _line_distance(_vec(c.Location()),_vec(d.Location()),axis)<EPS:return True
        elif face.geomType()=='PLANE':
            c,d=a.Plane(),b.Plane();n=_vec(c.Axis().Direction())
            if abs(np.dot(n,_vec(d.Axis().Direction())))>1-1e-8 and abs(np.dot(_vec(c.Location())-_vec(d.Location()),n))<EPS:return True
    return False

def default_settings(panels,width=15.):
    # Merge only planar neighbours that remain non-overlapping. Curved
    # interfaces stay separate and receive their dedicated patterns later.
    from .seams import adjacency
    from .seam_plans import automatic_planar_folds,propose
    from .panels import NetError
    _,pairs=adjacency(panels)
    folds=automatic_planar_folds(panels)
    try:return propose(dict(panels=panels),dict(fold_seam_ids=folds,overlap_width_mm=width))['settings']
    except NetError:
        return dict(fold_seam_ids=folds,cut_seam_ids=[],
                    seam_overrides=[dict(id=s['id'],kind='join',overlap_owner_panel=s['overlap_owner_panel'],width_mm=width) for s in pairs if s['id'] not in folds],
                    corner_relief_mode='native_boundary')

def generate(parameters,model,revision,output=None,previous=None):
    started=time.perf_counter()
    def phase(name):print('feature_composite stage='+name+' elapsed_s='+str(round(time.perf_counter()-started,3)),flush=True)
    phase('validate')
    validate('blanket',parameters)
    if parameters['model_ref']!=model.model_ref:raise BlanketError('needs_reselection: model revision mismatch')
    if parameters['included_faces'] or parameters['excluded_faces']:
        raise BlanketError('feature_cover_requires_complete_target_instances')
    if parameters['openings']:raise BlanketError('feature_cover_explicit_openings_unsupported')
    occurrences={o.id:o for o in model.occurrences};targets=parameters['target_instances'];excluded_ids=parameters.get('excluded_instances',[])
    if any(i not in occurrences for i in [*targets,*excluded_ids]):raise BlanketError('needs_reselection: unknown occurrence')
    ids=[i for i in targets if i not in excluded_ids]
    if not ids:raise BlanketError('feature_cover_requires_target_instances')
    selected=[occurrences[i] for i in ids]
    installation=parameters.get('installation_face')
    if not installation:raise BlanketError('feature_cover_requires_planar_installation_face')
    occurrence,installation_face,_=model.resolve(installation)
    if occurrence.id not in ids:raise BlanketError('installation_face_must_belong_to_selected_target')
    if installation_face.geomType()!='PLANE':raise BlanketError('installation_requires_plane')
    frame=Frame(parameters['installation_frame'])
    from .regular_cover import _bounds
    low,high=_bounds(frame.local(installation_face.copy()))
    if abs(low[2])>EPS or abs(high[2])>EPS:raise BlanketError('installation_frame_must_match_selected_plane')
    if len(selected)+len(excluded_ids)>16 or sum(len(o.shape.Faces()) for o in [*selected,*[occurrences[i] for i in excluded_ids]])>2000:raise BlanketError('feature_geometry_budget')
    if any(not o.shape.isValid() or not o.shape.Solids() for o in selected):raise BlanketError('feature_cover_requires_valid_solids')
    phase('recognize')
    original_hashes={o.id:shape_hash(o.shape) for o in selected};parts=[];refs=[]
    working=[o.shape.copy() for o in selected]
    if any(frame.local(shape.copy()).BoundingBox().zmin<-10*EPS for shape in working):
        raise BlanketError('installation_direction_must_face_selected_object')
    for o,shape in zip(selected,working):
        for part in recognize(shape):
            part['id']='feature-'+str(len(parts)+1);part['instance_id']=o.id
            part['support_face_ids']=[o.refs[i]['entity_id'] for i in part['support']]
            refs.append([o.refs[i] for i in part['support']]);parts.append(part)
    # A conservative uniform factor keeps circles native under anisotropic
    # requested allowances and never shrinks any primitive or its source.
    phase('native_union')
    factor=max(parameters['allowance']['factors']);native_parts=[_primitive(p,factor) for p in parts]
    base=_clip_to_installation_side(_union([_primitive(p,1.) for p in parts]),frame)
    envelope=_clip_to_installation_side(_union(native_parts),frame)
    phase('coverage')
    source=cq.Compound.makeCompound(working);outside=boolean(BRepAlgoAPI_Cut,source,envelope)
    outside_volume=sum(s.Volume() for s in outside.Solids())
    if outside_volume>max(1e-5,source.Volume()*1e-9):raise BlanketError('feature_cover_unrecognized_source_geometry: native coverage failed')
    phase('native_charts')
    evaluation_faces=envelope.Faces();installation_caps=_installation_caps(envelope,frame)
    native=[f for f in evaluation_faces if not any(f.isSame(cap) for cap in installation_caps)];opening_report=[]
    if excluded_ids:
        from .regular_cover import _auto_openings
        from .openings import face as opening_face
        from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
        from shapely.geometry import Polygon
        specs={}
        for index,f in enumerate(native):
            key='exterior-'+str(index);m,patches,_=partition(f)
            if f.geomType()!='PLANE':continue
            if len(patches)!=1:raise BlanketError('feature_opening_chart_unsupported')
            specs[key]=dict(face=f,outer=patches[0]['loops'][0],origin=(np.array(m['origin'])+m['u_origin']*np.array(m['x_axis'])).tolist(),u=m['x_axis'],v=m['y_axis'],index=index,domain=Polygon(patches[0]['loops'][0]['points'],[h['points'] for h in patches[0]['loops'][1:]]))
        excluded=[(occurrences[i],occurrences[i].shape.copy()) for i in excluded_ids]
        for occurrence,solid in excluded:
            if not solid.isValid():raise BlanketError('feature_excluded_requires_valid_geometry')
            for f in native:
                if f.geomType()!='PLANE' and sum(g.Area() for g in boolean(BRepAlgoAPI_Common,solid,f).Faces())>1e-7:
                    raise BlanketError('feature_opening_on_curved_surface_unsupported: excluded part requires a supported planar cover face')
        identity_frame=Frame(dict(origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0],z_axis=[0,0,1],units='mm',handedness='right'))
        automatic,opening_report=_auto_openings(parameters,excluded,specs,identity_frame)
        for opening in automatic:
            spec=specs[opening['panel']];poly=Polygon(opening['loop']['points'])
            if not spec['domain'].contains(poly) or spec['domain'].boundary.distance(poly)<=EPS:raise BlanketError('opening_crosses_cover_edge_or_existing_hole')
            placement=lambda p:[spec['origin'][i]+spec['u'][i]*p[0]+spec['v'][i]*p[1] for i in range(3)]
            cut=boolean(BRepAlgoAPI_Cut,native[spec['index']],opening_face(opening['loop']['points'],placement))
            if len(cut.Faces())!=1 or not cut.isValid():raise BlanketError('feature_opening_native_cut_failed')
            native[spec['index']]=cut.Faces()[0]
            spec['domain']=spec['domain'].difference(poly)
    panels=[];owners=[]
    for index,f in enumerate(native):
        if f.geomType() not in ('PLANE','CYLINDER'):raise BlanketError('feature_exterior_not_developable')
        owner=next((i for i,s in enumerate(native_parts) if _supported_by(f,s)),None)
        if owner is None:raise BlanketError('feature_exterior_owner_unresolved')
        m,patches,evidence=partition(f,(),parameters.get('surface_options',{}).get('chart_chord_mm',.02))
        if len(patches)!=1:raise BlanketError('feature_exterior_chart_partition_unsupported')
        patch=patches[0];key=parts[owner]['id']+'-face-'+str(index+1);o=np.array(m['origin'])+m['u_origin']*np.array(m['x_axis'])
        frame=dict(origin=o.tolist(),x_axis=m['x_axis'],y_axis=m['y_axis'],z_axis=m['z_axis'],units='mm',handedness='right')
        samples=[dict(flat_mm=xy,world_mm=xyz) for e in evidence['native_edges'] for xy,xyz in zip(e['flat_mm'],e['world_mm'])]
        panel=dict(id=revision+':'+key,key=key,feature_id=parts[owner]['id'],surface_ref='panels/'+key+'.brep',
                   outer_loop=patch['loops'][0],holes=patch['loops'][1:],frame=frame,source_refs=copy.deepcopy(refs[owner]),
                   mapping_ref=revision+':'+key+':native',surface_trim=dict(evidence=evidence,native_area_mm2=f.Area(),flat_area_mm2=patch['flat_area_mm2'],native_boundary_samples=samples))
        if f.geomType()!='PLANE':panel['surface_mapping']=m
        panels.append(panel);owners.append(owner)
    # Shared native TopoDS edges identify all interfaces, including inner wires
    # and BSpline intersections that the straight-edge tab editor cannot pair.
    interfaces=[]
    for i,f in enumerate(native):
        for j,g in enumerate(native[i+1:],i+1):
            common=[e for e in f.Edges() if any(e.isSame(other) for other in g.Edges())]
            if not common:continue
            curve_types=sorted(set(e.geomType() for e in common))
            interfaces.append(dict(id='interface-'+str(len(interfaces)+1),feature_ids=sorted(set([parts[owners[i]]['id'],parts[owners[j]]['id']])),
                                   panel_keys=[panels[i]['key'],panels[j]['key']],kind='feature_interface' if owners[i]!=owners[j] else 'feature_face_boundary',
                                   native_curve_types=curve_types,length_mm=sum(e.Length() for e in common),
                                   treatment='segmented_fan_tab_candidate' if curve_types==['CIRCLE'] else 'planar_fold_or_join',
                                   overlap_status='candidate_needs_material_sample' if curve_types==['CIRCLE'] else 'resolved_by_net_seams'))
    phase('report')
    from .unfold import unfold
    defaults=default_settings(panels,parameters.get('feature_overlap_mm',15.))
    default_net=unfold(panels,defaults)
    counts=summary(parameters,len(default_net['pieces']));ratio=envelope.Volume()/base.Volume()
    identity=dict(model_ref=model.model_ref,target_instances=sorted(ids),excluded_instances=sorted(excluded_ids),policy=POLICY,construction_version='native-serial-feature-union-installation-open-v2',source_hashes=original_hashes)
    baseline=dict(id='baseline-'+fingerprint(identity),source_revision=revision,algorithm=ALGORITHM,
                  parameters=dict(identity=identity,volume_definition='Native union of recognized enclosing analytic primitives before allowance, clipped at the installation plane; source recesses are filled'),
                  closed_shape_ref='baseline.brep',volume_mm3=base.Volume(),openings_closure=['installation-bottom-evaluation-only'],confirmed_revision=revision)
    baseline=json.loads(canonical(baseline))
    if previous and previous['id']==baseline['id']:
        expected=copy.deepcopy(baseline);expected.update(source_revision=previous['source_revision'],confirmed_revision=previous['confirmed_revision'])
        if expected!=previous:raise BlanketError('baseline_integrity')
        baseline=copy.deepcopy(previous)
    circular_interfaces=any(i['native_curve_types']==['CIRCLE'] for i in interfaces)
    feature_report=dict(features=[dict(id=p['id'],kind=p['kind'],label=p['label'],instance_id=p['instance_id'],support_face_ids=p['support_face_ids'],parameters={k:v for k,v in p.items() if k not in ('id','support','support_face_ids','instance_id','label','kind')}) for p in parts],
                        interfaces=interfaces,primitive_count=len(parts),manufacturing_panel_count=len(panels),default_piece_count=len(default_net['pieces']),
                        uncovered_source_volume_mm3=outside_volume,excluded_instances=sorted(excluded_ids),openings=opening_report,internal_surface_policy='union_exterior_only',
                        allowance_policy='uniform_conservative_maximum_requested_factor',effective_allowance_factor=factor,
                        interface_pattern_status='generated_draft_needs_material_sample' if circular_interfaces else 'resolved_by_planar_net',installation_surface_policy='selected_installation_plane_clipped_from_manufacturing',installation_opening=True,bottom_fixed=False,auto_fixed_points=parameters.get('auto_fixed_points',True))
    checks=[record('coverage',True,dict(outside_volume_mm3=outside_volume,source_faces=len(source.Faces())),'All original native source solids retained in containment Boolean','mm3'),
            record('topology',True,dict(manufacturing_faces=len(native),primitive_count=len(parts),internal_faces_removed=True,evaluation_caps=['installation-bottom']),'Only valid exterior faces above the installation plane are manufacturing panels; the installation cap is evaluation-only'),
            record('piece_limit',not counts['requirements_unmet'],counts,'Independent cutting pieces per layer'),
            record('volume_ratio',True,dict(ratio=ratio,reference=parameters.get('volume_ratio_reference',1.2),baseline_volume_mm3=base.Volume(),cover_volume_mm3=envelope.Volume()),'Volume allowance is an informational reference','ratio'),
            dict(record('unfolding',True,dict(state='requires_current_net'),'Native chart foldback checked on current net'),status='not_run'),
            dict(record('feature_interfaces',True,dict(interface_count=len(interfaces),status='segmented_fan_tabs_generated_as_material_trial_draft' if circular_interfaces else 'resolved_by_planar_net'),'Planar interfaces use fold or joined seams; circular interfaces use segmented fan-tab drafts whose material behaviour still requires sample validation'),status='needs_review' if circular_interfaces else 'pass')]
    for c in checks:c['algorithm_version']=ALGORITHM
    bounds=envelope.BoundingBox();result=dict(schema_version=1,revision_id=revision,model_ref=copy.deepcopy(model.model_ref),parameters=copy.deepcopy(parameters),baseline=baseline,
        dimensions_mm=[bounds.xlen,bounds.ylen,bounds.zlen],panels=panels,native_shape_ref='manufacturing.brep',evaluation_shape_ref='evaluation.brep',display_ref='cover.glb',
        closures=[dict(id='installation-bottom',shape_ref='closures/installation-bottom.brep',evaluation_only=True)],checks=checks,
        status='failed' if counts['requirements_unmet'] else 'needs_review',candidate_editable=True,algorithm_version=ALGORITHM,
        downstream=dict(revision_id=revision,panels='candidates',unfolding='not_computed',checks_revision=revision),manufacturing_summary=counts,feature_composite=feature_report)
    if original_hashes!={o.id:shape_hash(o.shape) for o in selected}:raise BlanketError('source_mutated')
    validate('blanket',result,'BlanketResult')
    phase('artifacts')
    if output is not None:
        output.mkdir(parents=True,exist_ok=True);(output/'panels').mkdir(exist_ok=True);(output/'closures').mkdir(exist_ok=True)
        base.exportBrep(str(output/'baseline.brep'));envelope.exportBrep(str(output/'evaluation.brep'))
        cq.Compound.makeCompound(installation_caps).exportBrep(str(output/'closures/installation-bottom.brep'))
        cq.Compound.makeCompound(native).exportBrep(str(output/'manufacturing.brep'));assembly=cq.Assembly()
        colors=[(.30,.58,.76),(.89,.68,.27),(.4,.66,.36),(.5,.76,.65),(.71,.4,.70),(.83,.53,.79),(.81,.4,.36),(.89,.63,.43)]
        for panel,actual,owner in zip(panels,native,owners):
            actual.exportBrep(str(output/panel['surface_ref']));assembly.add(actual,name=panel['id'].replace(':','_'),color=cq.Color(*colors[owner%len(colors)]))
        assembly.export(str(output/'cover.glb'))
        from .display import normalize
        normalize(output/'cover.glb',panels);(output/'blanket-result.json').write_text(canonical(result))
    phase('complete')
    return result
