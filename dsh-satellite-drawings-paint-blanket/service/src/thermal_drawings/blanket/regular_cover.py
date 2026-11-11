"""Regular, bottom-open covers for explicitly selected assembly occurrences.

The retained analytic cylindrical side uses the existing isometric chart path.
Volume ratio is informational; final independent cutting pieces are a hard limit.
"""
import copy
import math
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient
from .selection import Frame, BlanketError, shape_hash
from .checks import boolean, record
from .openings import face, cut_openings
from .surface_charts import descriptor, partition
from .unfold import unfold
from ..domain.validation import canonical, fingerprint, validate

ALGORITHM = 'regular-cover-v1'
POLICIES = ('regular_box_v1', 'regular_cylinder_v1')


def summary(parameters, count):
    limit = parameters.get('piece_limit', 10)
    layers = parameters.get('layer_count', 1)
    unmet = ['piece_limit_exceeded'] if count > limit else []
    return dict(pieces_per_layer=count, layer_count=layers, total_pieces=count*layers,
                piece_limit=limit, limit_reached=count >= limit, requirements_unmet=unmet,
                count_basis='final_cut_pieces')


def _measure_target_volume(local):
    """Net union volume of included source solids; no regular-shell substitution.

    A bounded optional measurement must not hold up an otherwise usable cover.
    Failed Boolean results are reported as unavailable rather than silently
    summing overlapping assembly solids.
    """
    solids = [solid for shape in local for solid in shape.Solids()]
    report = dict(status='unavailable', method='native_solid_union_net_volume',
                  source_solid_count=len(solids), overlaps='counted_once_by_union',
                  cavities='excluded_from_net_volume', excluded_instances='not_included')
    if len(solids) > 64 or sum(len(s.Faces()) for s in solids) > 5000:
        return None, dict(report, reason='optional_volume_measurement_budget')
    if not solids or any(not s.isValid() or not s.outerShell().Closed() for s in solids):
        return None, dict(report, reason='source_solids_not_valid_and_closed')
    try:
        native = solids[0] if len(solids)==1 else boolean(BRepAlgoAPI_Fuse, solids[0], cq.Compound.makeCompound(solids[1:]))
        retained = native.Solids()
        if (not native.isValid() or not retained or any(not s.isValid() or not s.outerShell().Closed() for s in retained)
                or sum(len(s.Faces()) for s in retained) != len(native.Faces())):
            return None, dict(report, reason='union_not_valid_closed_solids')
        value = sum(s.Volume() for s in retained)
        original = [s.Volume() for s in solids]
        tolerance = max(1e-6, sum(original)*1e-9)
        if (not math.isfinite(value) or value <= 0 or value > sum(original)+tolerance
                or value < max(original)-tolerance):
            return None, dict(report, reason='union_volume_consistency_failed')
        return value, dict(report, status='measured', union_solid_count=len(retained))
    except Exception:
        return None, dict(report, reason='native_union_measurement_failed')


def _bounds(shape):
    from .faceted_cover import native_bounds
    b = native_bounds(shape)
    return list(b[:3]), list(b[3:])


def _circle(center, radius, count=128, clockwise=False):
    sign = -1 if clockwise else 1
    return [[center[0]+radius*math.cos(sign*2*math.pi*i/count),
             center[1]+radius*math.sin(sign*2*math.pi*i/count)] for i in range(count)]


def _ring(points, clockwise=False):
    poly = orient(Polygon(points), sign=-1 if clockwise else 1)
    return dict(points=[list(p) for p in list(poly.exterior.coords)[:-1]], closed=True,
                orientation='cw' if clockwise else 'ccw')


def _panel(revision, key, actual, outer, holes, origin, u, v, frame, refs):
    n = cq.Vector(*u).cross(cq.Vector(*v)).toTuple()
    o = frame.point(origin)
    direction = lambda a: [p-q for p,q in zip(frame.point([origin[i]+a[i] for i in range(3)]), o)]
    return dict(id=f'{revision}:{key}', key=key, surface_ref=f'panels/{key}.brep',
                outer_loop=outer, holes=holes,
                frame=dict(origin=o, x_axis=direction(u), y_axis=direction(v), z_axis=direction(n), units='mm', handedness='right'),
                source_refs=refs, mapping_ref=f'{revision}:{key}:regular')


def _auto_openings(parameters, excluded, specs, frame):
    options = parameters.get('opening_options', {})
    shape = options.get('shape', 'rectangle')
    padding = options.get('padding_mm', 0.)
    scale = options.get('size_scale', 1.)
    result = []; report = []
    for occurrence, solid in excluded:
        hits = []
        for key, spec in specs.items():
            common = boolean(BRepAlgoAPI_Common, solid, spec['face'])
            if sum(f.Area() for f in common.Faces()) > 1e-7:
                hits.append((key, spec, common))
        if len(hits) > 1:
            raise BlanketError('opening_crosses_multiple_cover_faces: first version supports one planar cover face per excluded instance')
        if not hits:
            report.append(dict(instance_id=occurrence.id, status='no_cover_intersection'))
            continue
        key, spec, section = hits[0]
        if key == 'cylinder-side':
            raise BlanketError('opening_on_cylinder_side_unsupported: first version supports cylinder top only')
        origin, u, v = spec['origin'], spec['u'], spec['v']
        # Bounding the actual native plane section avoids using an entire tall
        # or inclined excluded part to size its aperture.
        placement = Frame(dict(origin=origin,x_axis=u,y_axis=v,
                               z_axis=list(cq.Vector(*u).cross(cq.Vector(*v)).toTuple()),units='mm',handedness='right'))
        lo, hi = _bounds(placement.local(section))
        center = [(lo[i]+hi[i])/2 for i in range(2)]
        sizes = [(hi[i]-lo[i])*scale+2*padding for i in range(2)]
        if shape == 'circle':
            edges = section.Edges()
            is_circle = bool(edges) and all(e.geomType() == 'CIRCLE' for e in edges) and abs(sizes[0]-sizes[1]) < 1e-5
            radius = max(sizes)/2 if is_circle else math.hypot(*sizes)/2
            # The common 3D/2D polygon circumscribes the requested circle;
            # it never clips a circular part between adjacent sample points.
            radius /= math.cos(math.pi/128)
            points = _circle(center, radius)
            sizes = [2*radius, 2*radius]
        else:
            x,y = center; w,h = sizes
            points = [[x-w/2,y-h/2],[x+w/2,y-h/2],[x+w/2,y+h/2],[x-w/2,y+h/2]]
        poly = Polygon(points); domain = Polygon(spec['outer']['points'])
        if not domain.contains(poly) or domain.boundary.distance(poly) <= 1e-6:
            raise BlanketError('opening_crosses_cover_edge: opening must stay strictly inside one supported planar face')
        opening = dict(id='excluded:'+occurrence.id, panel=key, loop=_ring(points))
        result.append(opening)
        report.append(dict(id=opening['id'], instance_id=occurrence.id, panel=key, shape=shape,
                           center_uv_mm=center, size_mm=sizes, status='created', boundary_representation='shared_128_segment_circumscribed_circle' if shape=='circle' else 'rectangle'))
    return result, report


def generate(parameters, model, revision, output=None, previous=None):
    validate('blanket', parameters)
    if parameters['model_ref'] != model.model_ref:
        raise BlanketError('needs_reselection: model revision mismatch')
    if parameters['included_faces'] or parameters['excluded_faces']:
        raise BlanketError('regular_cover_uses_instance_scope: select target and excluded instances')
    ids = parameters['target_instances']; excluded_ids = parameters.get('excluded_instances', [])
    occurrences = {o.id:o for o in model.occurrences}
    if any(i not in occurrences for i in [*ids,*excluded_ids]):
        raise BlanketError('needs_reselection: unknown occurrence')
    included = [occurrences[i] for i in ids if i not in excluded_ids]
    if not included:
        raise BlanketError('regular_cover_requires_target_instances')
    # Excluded geometry participates in plane intersections and must obey the
    # same pre-copy budget as the target; a small target must not admit a huge
    # excluded assembly into repeated native Booleans.
    active = [*included, *[occurrences[i] for i in excluded_ids]]
    if len(active) > 128 or sum(len(o.shape.Faces()) for o in active) > 20000:
        raise BlanketError('regular_cover_geometry_budget: choose a smaller object')
    frame = Frame(parameters['installation_frame'])
    installation = parameters.get('installation_face')
    if not installation:
        raise BlanketError('regular_cover_requires_planar_installation_face')
    occ, installation_face, _ = model.resolve(installation)
    if occ.id not in {o.id for o in included}:
        raise BlanketError('installation_face_must_belong_to_selected_target: choose a plane on the included object')
    if installation_face.geomType() != 'PLANE':
        raise BlanketError('installation_requires_plane')
    plane_lo, plane_hi = _bounds(frame.local(installation_face.copy()))
    if abs(plane_lo[2]) > 1e-5 or abs(plane_hi[2]) > 1e-5:
        raise BlanketError('installation_frame_must_match_selected_plane')
    local = [frame.local(o.shape.copy()) for o in included]
    if any(not s.isValid() or not s.Solids() for s in local):
        raise BlanketError('regular_cover_requires_valid_solids')
    source = cq.Compound.makeCompound(local)
    low, high = _bounds(source)
    if low[2] < -1e-5 or high[2] <= 1e-6:
        raise BlanketError('installation_direction_must_face_selected_object')
    cx,cy = [(low[i]+high[i])/2 for i in range(2)]
    x,y,h = high[0]-low[0], high[1]-low[1], high[2]
    factors = parameters['allowance']['factors']
    cylinder = parameters['envelope_policy'] == 'regular_cylinder_v1'
    radius = math.hypot(x,y)/2
    if cylinder:
        # An aligned cylinder keeps its real circular bound rather than using
        # the diagonal of its square bounding box.
        radial = []
        for solid in local:
            outer_faces = solid.Solids()[0].outerShell().Faces() if len(solid.Solids())==1 else []
            fs = [f for f in outer_faces if f.geomType() == 'CYLINDER']
            if len(outer_faces)!=3 or len(fs)!=1 or any(f.geomType() not in ('CYLINDER','PLANE') for f in outer_faces):break
            c = BRepAdaptor_Surface(fs[0].wrapped).Cylinder(); axis=c.Axis().Direction(); p=c.Location()
            if abs(abs(axis.Z())-1)>1e-9:break
            lo,hi=_bounds(solid)
            if any(abs((hi[i]-lo[i])-2*c.Radius())>1e-5 for i in range(2)):break
            radial.append(math.hypot(p.X()-cx,p.Y()-cy)+c.Radius())
        else:
            if radial:radius=max(radial)
        baseline_shape = cq.Solid.makeCylinder(radius,h,cq.Vector(cx,cy,0))
        radius *= max(factors[:2]); h *= factors[2]; x=y=2*radius
        envelope_shape = cq.Solid.makeCylinder(radius,h,cq.Vector(cx,cy,0))
    else:
        baseline_shape = cq.Solid.makeBox(x,y,h,cq.Vector(cx-x/2,cy-y/2,0))
        x*=factors[0]; y*=factors[1]; h*=factors[2]
        envelope_shape = cq.Solid.makeBox(x,y,h,cq.Vector(cx-x/2,cy-y/2,0))
    if parameters.get('dimensions_mm') is not None:
        raise BlanketError('regular_cover_dimensions_derived_from_allowance')
    refs = [r for o in included for r in o.refs]
    specs = {}; xmin=cx-x/2; ymin=cy-y/2
    if not cylinder:
        definitions = {'x-':([xmin,ymin,0],[0,0,1],[0,1,0],h,y),
                       'x+':([xmin+x,ymin,0],[0,1,0],[0,0,1],y,h),
                       'y-':([xmin,ymin,0],[1,0,0],[0,0,1],x,h),
                       'y+':([xmin,ymin+y,0],[0,0,1],[1,0,0],h,x),
                       'z+':([xmin,ymin,h],[1,0,0],[0,1,0],x,y)}
        for key,(origin,u,v,w,t) in definitions.items():
            outer=_ring([[0,0],[w,0],[w,t],[0,t]])
            placement=lambda p,o=origin,a=u,b=v:[o[i]+a[i]*p[0]+b[i]*p[1] for i in range(3)]
            specs[key]=dict(face=face(outer['points'],placement),outer=outer,origin=origin,u=u,v=v,width=w,height=t)
    else:
        side=next(f for f in envelope_shape.Faces() if f.geomType()=='CYLINDER')
        top=next(f for f in envelope_shape.Faces() if f.geomType()=='PLANE' and abs(f.Center().z-h)<1e-5)
        specs['cylinder-side']=dict(face=side)
        specs['z+']=dict(face=top,outer=_ring(_circle([0,0],radius)),origin=[cx,cy,h],u=[1,0,0],v=[0,1,0])
    excluded = [(occurrences[i],frame.local(occurrences[i].shape.copy())) for i in excluded_ids]
    automatic, opening_report = _auto_openings(parameters,excluded,specs,frame)
    all_openings = [*parameters['openings'],*automatic]
    if len({o['id'] for o in all_openings})!=len(all_openings):raise BlanketError('duplicate opening ID')
    if any(o['panel'] not in specs or o['panel']=='cylinder-side' for o in all_openings):
        raise BlanketError('opening_requires_supported_planar_cover_face')
    panels=[]; native=[]
    for key,spec in specs.items():
        world_face=frame.world(spec['face'])
        if key=='cylinder-side':
            mapping, patches, evidence = partition(world_face,())
            if len(patches)!=1:raise BlanketError('regular_cylinder_chart_failed')
            patch=patches[0]
            panel=_panel(revision,key,world_face,patch['loops'][0],patch['loops'][1:],[0,0,0],[1,0,0],[0,1,0],Frame(dict(origin=[0,0,0],x_axis=[1,0,0],y_axis=[0,1,0],z_axis=[0,0,1],units='mm',handedness='right')),refs)
            panel.update(surface_mapping=mapping,surface_trim=dict(evidence=evidence,native_area_mm2=world_face.Area(),flat_area_mm2=patch['flat_area_mm2']))
        else:
            holes=[o for o in all_openings if o['panel']==key]
            placement=lambda p,s=spec:[s['origin'][i]+s['u'][i]*p[0]+s['v'][i]*p[1] for i in range(3)]
            if not cylinder:
                actual,_,rings=cut_openings(spec['width'],spec['height'],holes,placement)
            else:
                domain=Polygon(spec['outer']['points']); polys=[]
                for opening in holes:
                    poly=Polygon(opening['loop']['points'])
                    if not poly.is_valid or not domain.contains(poly) or domain.boundary.distance(poly)<=1e-6 or any(poly.intersects(p) for p in polys):raise BlanketError('invalid_opening')
                    polys.append(poly)
                rings=[_ring(list(p.exterior.coords)[:-1],True) for p in polys]
                actual=cq.Face.makeFromWires(spec['face'].outerWire(),[face(r['points'],placement).outerWire() for r in rings])
            world_face=frame.world(actual)
            panel=_panel(revision,key,world_face,spec['outer'],rings,spec['origin'],spec['u'],spec['v'],frame,refs)
        panels.append(panel);native.append(world_face)
    # Match the workbench's primary connected-15mm action, not the unrelated
    # default fold forest. If that bounded proposal cannot fit, report the
    # conservative separate-piece count and keep the cover inspectable.
    from .seam_plans import propose
    from .panels import NetError
    count_plan='connected_15mm_v1';count_warning=None
    try:
        proposed=propose(dict(panels=panels))
        default_net=unfold(panels,proposed['settings'])
        count=len(default_net['pieces'])
    except NetError as error:
        count=len(panels);count_plan='separate_panels'
        count_warning=str(error)
    counts=summary(parameters,count)
    outside=boolean(BRepAlgoAPI_Cut,source,envelope_shape)
    outside_volume=sum(s.Volume() for s in outside.Solids())
    ratio=envelope_shape.Volume()/baseline_shape.Volume()
    reference=parameters.get('volume_ratio_reference',1.2)
    target_volume, target_measurement = _measure_target_volume(local)
    identity=dict(model_ref=model.model_ref,target_instances=sorted(o.id for o in included),installation_frame=parameters['installation_frame'],policy=parameters['envelope_policy'],source_hashes={o.id:shape_hash(o.shape) for o in included})
    baseline=dict(id='baseline-'+fingerprint(identity),source_revision=revision,algorithm=ALGORITHM,parameters=dict(identity=identity,dimensions_mm=[high[0]-low[0],high[1]-low[1],high[2]],volume_definition='Closed regular envelope of included instances before linear allowance; assembly gaps and cavities are included'),closed_shape_ref='baseline.brep',volume_mm3=baseline_shape.Volume(),openings_closure=[],confirmed_revision=revision)
    baseline=__import__('json').loads(canonical(baseline))
    if previous and previous['id']==baseline['id']:
        expected=copy.deepcopy(baseline);expected.update(source_revision=previous['source_revision'],confirmed_revision=previous['confirmed_revision'])
        if expected!=previous:raise BlanketError('baseline_integrity')
        baseline=copy.deepcopy(previous)
    checks=[record('coverage',outside_volume<1e-5,dict(outside_volume_mm3=outside_volume),'Included source solids must fit inside the regular cover','mm3'),
            record('topology',all(f.isValid() for f in native),dict(manufacturing_faces=len(native),analytic_cylinder_retained=cylinder),'Valid native manufacturing faces'),
            record('piece_limit',not counts['requirements_unmet'],counts,'Hard limit counts independent final cutting pieces per layer'),
            record('volume_ratio',True,dict(ratio=ratio,reference=reference,reference_exceeded=ratio>reference,baseline_volume_mm3=baseline_shape.Volume(),cover_volume_mm3=envelope_shape.Volume(),volume_definition=baseline['parameters']['volume_definition']),'Volume ratio is an adjustable reference; exceeding it permits this regular cover','ratio')]
    checks.append(dict(record('unfolding',True,dict(state='requires_current_net'),'Final topology and foldback are checked on the matching net'),status='not_run'))
    for check in checks:check['algorithm_version']=ALGORITHM
    regular=dict(shape='cylinder' if cylinder else 'box',dimensions_mm=[x,y,h],volume_ratio=ratio,volume_ratio_reference=reference,volume_reference_exceeded=ratio>reference,openings=opening_report,bottom_fixed=True)
    regular.update(piece_count_plan=count_plan,piece_count_warning=count_warning,
                   envelope_volume_mm3=envelope_shape.Volume(), target_volume_mm3=target_volume,
                   envelope_to_target_volume_ratio=envelope_shape.Volume()/target_volume if target_volume is not None else None,
                   target_volume_measurement=target_measurement,
                   volume_ratio_metric='allowance_envelope_volume_ratio',
                   volume_ratio_reference_metric='allowance_envelope_volume_ratio')
    if cylinder:regular['diameter_mm']=2*radius
    result=dict(schema_version=1,revision_id=revision,model_ref=copy.deepcopy(model.model_ref),parameters=copy.deepcopy(parameters),baseline=baseline,dimensions_mm=[x,y,h],panels=panels,native_shape_ref='manufacturing.brep',evaluation_shape_ref='evaluation.brep',display_ref='cover.glb',closures=[dict(id='closed-regular-evaluation-envelope',shape_ref='closures/evaluation-shell.brep',evaluation_only=True)],checks=checks,status='failed' if any(c['status']=='fail' for c in checks) else 'passed',candidate_editable=True,algorithm_version=ALGORITHM,downstream=dict(revision_id=revision,panels='candidates',unfolding='not_computed',checks_revision=revision),manufacturing_summary=counts,regular_envelope=regular)
    validate('blanket',result,'BlanketResult')
    if output is not None:
        output.mkdir(parents=True,exist_ok=True);(output/'panels').mkdir(exist_ok=True);(output/'closures').mkdir(exist_ok=True)
        frame.world(baseline_shape).exportBrep(str(output/'baseline.brep'))
        for path in ['evaluation.brep','closures/evaluation-shell.brep']:frame.world(envelope_shape).exportBrep(str(output/path))
        cq.Compound.makeCompound(native).exportBrep(str(output/'manufacturing.brep'));assembly=cq.Assembly()
        for panel,actual in zip(panels,native):
            actual.exportBrep(str(output/panel['surface_ref']));assembly.add(actual,name=panel['id'].replace(':','_'),color=cq.Color(.75,.65,.25))
        assembly.export(str(output/'cover.glb'))
        from .display import normalize
        normalize(output/'cover.glb',panels);(output/'blanket-result.json').write_text(canonical(result))
    return result
