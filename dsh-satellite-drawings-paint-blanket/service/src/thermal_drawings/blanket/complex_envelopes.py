"""Exact orthogonal section envelopes; holes are explicitly capped, concavity retained.

Cell classification is exact for the admitted axis-aligned planar/linear BRep
family. No tessellation or material volume is used as the denominator.
"""
import copy
import json
import math
import cadquery as cq
from shapely.geometry import box as rectangle, Polygon
from shapely.ops import unary_union
from shapely.affinity import scale
from ..domain.validation import fingerprint, validate, canonical
from ..paint.selection import Plane, loops
from .selection import Frame, BlanketError, shape_hash, bounds, EPS
from .checks import boolean, record
from .volume import ratio_check
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Common
from OCP.BRepTools import BRepTools_WireExplorer

ALGORITHM = 'b13-orthogonal-sections-v1'


def polygons(g):
    return [g] if g.geom_type == 'Polygon' else list(g.geoms)


def levels(values):
    result=[]
    for v in sorted(values):
        if not result or v-result[-1]>EPS:result.append(v)
    return result


def profiles(source):
    if not source.isValid() or not source.Solids():
        raise BlanketError('invalid_complex_source')
    for f in source.Faces():
        if f.geomType()!='PLANE' or any(e.geomType()!='LINE' for e in f.Edges()):
            raise BlanketError('orthogonal_sections_require_planar_linear_geometry')
        n=f.normalAt()
        if max(abs(v) for v in n.toTuple()) < 1-1e-10:
            raise BlanketError('orthogonal_sections_require_aligned_axes')
    vertices=[v.Center().toTuple() for v in source.Vertices()]
    axes=[levels([p[i] for p in vertices]) for i in range(3)]
    if math.prod(len(a)-1 for a in axes)>50000:raise BlanketError('section_cell_budget')
    result=[]
    for za,zb in zip(axes[2],axes[2][1:]):
        cells=[]
        for xa,xb in zip(axes[0],axes[0][1:]):
            for ya,yb in zip(axes[1],axes[1][1:]):
                p=cq.Vector((xa+xb)/2,(ya+yb)/2,(za+zb)/2)
                if any(s.isInside(p,1e-8) for s in source.Solids()):
                    cells.append(rectangle(xa,ya,xb,yb))
        if not cells:continue
        material=unary_union(cells)
        # All enclosed rings in every horizontal slice are evaluation cavities,
        # capped by this versioned Z-section convention, never material volume.
        exterior=unary_union([Polygon(p.exterior) for p in polygons(material)])
        result.append(dict(z=[za,zb],loops=[list(p.exterior.coords)[:-1] for p in polygons(exterior)],
                           filled_area_mm2=exterior.area-material.area))
    if not result:raise BlanketError('empty_complex_baseline')
    return result


def solid_from_profiles(sections,padding=(0,0,0)):
    dx,dy,dz=padding;solids=[]
    for s in sections:
        z0,z1=s['z'];z0=max(0,z0-dz);z1+=dz
        for pts in s['loops']:
            poly=Polygon(pts)
            if dx or dy:
                # Minkowski sum with an axis-aligned rectangle; no inward
                # scaling around a concavity, and anisotropic padding allowed.
                from shapely.affinity import translate
                pieces=[translate(poly,xoff=x,yoff=y) for x in (-dx,dx) for y in (-dy,dy)]
                for a,b in zip(pts,pts[1:]+pts[:1]):
                    from shapely.geometry import MultiPoint
                    pieces.append(MultiPoint([(p[0]+x,p[1]+y) for p in (a,b) for x in (-dx,dx) for y in (-dy,dy)]).convex_hull)
                poly=unary_union(pieces)
            for p in polygons(poly):
                wire=cq.Wire.makePolygon([cq.Vector(x,y,z0) for x,y in list(p.exterior.coords)[:-1]],close=True)
                holes=[cq.Wire.makePolygon([cq.Vector(x,y,z0) for x,y in list(h.coords)[:-1]],close=True) for h in p.interiors]
                solids.append(cq.Solid.extrudeLinear(wire,holes,cq.Vector(0,0,z1-z0)))
    result=solids[0]
    for s in solids[1:]:result=result.fuse(s)
    result=result.clean()
    if not result.isValid() or len(result.Solids())!=1:raise BlanketError('disconnected_or_invalid_envelope')
    return result.Solids()[0]


def panel_faces(solid,frame,revision,refs,source_faces,parameters):
    panels=[];native=[];caps=[]
    vertices=[v.Center() for v in solid.Vertices()]
    faces=sorted(solid.Faces(),key=lambda f:tuple(round(x,8) for x in (*f.normalAt().toTuple(),*f.Center().toTuple(),f.Area())))
    used=set()
    for face in faces:
        if abs(face.Center().z)<EPS and face.normalAt().z<-.99:
            caps.append(('installation-bottom',face));continue
        plane=Plane(face)
        # Preserve T-junction vertices so adjacency pairs complete subedges.
        def ring(wire):
            if all(e.geomType()=='LINE' for e in wire.Edges()):
                # Sampling a closed polyline can shift a corner onto its next
                # edge and introduce artificial subedges, losing real seams.
                explorer=BRepTools_WireExplorer(wire.wrapped,face.wrapped);pts=[]
                while explorer.More():
                    pts.append(cq.Vertex(explorer.CurrentVertex()).Center());explorer.Next()
            else:
                pts,_=wire.sample(1e-7)
                pts=[cq.Vector(*p.toTuple()) for p in pts]
            res=[]
            for a,b in zip(pts,pts[1:]+pts[:1]):
                delta=b-a;length=delta.Length
                if length<EPS:continue
                mids=[((v-a).dot(delta)/(length*length),v) for v in vertices
                      if (v-a).cross(delta).Length/length<EPS and EPS<(v-a).dot(delta)/length<length-EPS]
                res.append(plane.uv(a));res.extend(plane.uv(v) for _,v in sorted(mids,key=lambda x:x[0]))
            return res
        poly=Polygon(ring(face.outerWire()),[ring(w) for w in face.innerWires()])
        key='complex-'+fingerprint(dict(normal=face.normalAt().toTuple(),vertices=sorted(tuple(round(x,7) for x in v.Center().toTuple()) for v in face.Vertices())))[:18]
        distances=[(face.distance(f),r) for f,r in source_faces if f.normalAt().dot(face.normalAt())>.999999]
        minimum=min((d for d,_ in distances),default=math.inf)
        sources=[r for d,r in distances if abs(d-minimum)<EPS]
        if not sources:sources=refs
        excluded=bool(sources) and (all(r in parameters['excluded_faces'] for r in sources) or
                 bool(parameters['included_faces'] and not any(r in parameters['included_faces'] for r in sources)))
        if excluded:
            caps.append(('excluded:'+key,face));continue
        for o in parameters['openings']:
            if o['panel']!=key:continue
            used.add(o['id']);opening=Polygon(o['loop']['points'])
            if not opening.is_valid or opening.area<=EPS or not poly.contains(opening) or opening.boundary.distance(poly.boundary)<=EPS:
                raise BlanketError('opening_outside_complex_panel')
            poly=poly.difference(opening)
            from .net_native import face as make_face
            cap=make_face(o['loop']['points'],[],lambda uv:(plane.origin+plane.x*uv[0]+plane.y*uv[1]).toTuple())
            caps.append(('opening:'+o['id'],cap))
        if poly.geom_type!='Polygon':raise BlanketError('opening_splits_panel')
        rings=loops(poly)
        from .net_native import face as make_face
        actual=make_face(rings[0]['points'],[h['points'] for h in rings[1:]],lambda uv:(plane.origin+plane.x*uv[0]+plane.y*uv[1]).toTuple())
        world_frame=plane.frame();origin=frame.point(world_frame['origin'])
        for a in ['x_axis','y_axis','z_axis']:
            endpoint=frame.point([world_frame['origin'][i]+world_frame[a][i] for i in range(3)])
            world_frame[a]=[endpoint[i]-origin[i] for i in range(3)]
        world_frame['origin']=origin
        panels.append(dict(id=revision+':'+key,key=key,surface_ref='panels/'+key+'.brep',outer_loop=rings[0],
                           holes=rings[1:],frame=world_frame,source_refs=sources,mapping_ref=revision+':'+key+':planar'))
        native.append(actual)
    if used!={o['id'] for o in parameters['openings']}:raise BlanketError('needs_reselection: unknown or excluded opening panel')
    if not panels:raise BlanketError('empty_manufacturing_cover')
    return panels,native,caps


def generate(parameters,model,revision,output=None,previous=None):
    validate('blanket',parameters)
    if parameters['model_ref']!=model.model_ref:raise BlanketError('needs_reselection: model mismatch')
    if any(parameters[k] for k in ['cut_edges','fold_edges','overlaps','fixed_points']) or parameters['unfold_base_panel'] is not None:
        raise BlanketError('use_current_net_settings_for_cuts_and_points')
    if 'dimensions_mm' in parameters:raise BlanketError('complex_shape_uses_allowance_not_box_dimensions')
    selected=[o for o in model.occurrences if o.id in parameters['target_instances']]
    if len(selected)!=len(parameters['target_instances']):raise BlanketError('needs_reselection: occurrence mismatch')
    frame=Frame(parameters['installation_frame'])
    shape=cq.Compound.makeCompound([frame.local(o.shape.copy()) for o in selected])
    low,high=bounds(shape)
    if abs(low[2])>EPS:raise BlanketError('installation_bottom_mismatch')
    refs=[r for o in selected for r in o.refs]
    if any(r not in refs for k in ['included_faces','excluded_faces'] for r in parameters[k]):raise BlanketError('needs_reselection: foreign face')
    if any(r in parameters['excluded_faces'] for r in parameters['included_faces']):raise BlanketError('conflicting_face_selection')
    if parameters.get('installation_face'):
        _,f,_=model.resolve(parameters['installation_face']);f=frame.local(f)
        if parameters['installation_face'] not in refs or f.geomType()!='PLANE' or abs(f.Center().z)>EPS or f.normalAt().z>-.99:
            raise BlanketError('needs_reselection: installation face')
    sections=profiles(shape);base=solid_from_profiles(sections)
    identity=dict(model_ref=model.model_ref,instances=parameters['target_instances'],frame=parameters['installation_frame'],
                  source_hashes={o.id:shape_hash(o.shape) for o in selected},algorithm=ALGORITHM)
    baseline=dict(id='baseline-'+fingerprint(identity),source_revision=revision,algorithm=ALGORITHM,
                  parameters=dict(identity=identity,sections=sections,closure_policy='fill bounded rings in each Z section; keep exterior concavities'),
                  closed_shape_ref='baseline.brep',volume_mm3=base.Volume(),
                  openings_closure=['section-interior-rings','installation-bottom-evaluation-only'],confirmed_revision=revision)
    baseline=json.loads(canonical(baseline))
    if previous and previous['id']==baseline['id']:
        expected=copy.deepcopy(baseline);expected.update(source_revision=previous['source_revision'],confirmed_revision=previous['confirmed_revision'])
        if expected!=previous:raise BlanketError('baseline_integrity')
        baseline=copy.deepcopy(previous)
    dims=[b-a for a,b in zip(low,high)]
    factors=parameters['allowance']['factors']
    if any(not math.isfinite(f) or f<1 or f>2 for f in factors):raise BlanketError('complex_allowance_range')
    padding=[dims[0]*(factors[0]-1)/2,dims[1]*(factors[1]-1)/2,dims[2]*(factors[2]-1)]
    solid=solid_from_profiles(sections,padding)
    source_faces=[(frame.local(f),r) for o in selected for f,r in zip(o.shape.Faces(),o.refs)]
    panels,native,caps=panel_faces(solid,frame,revision,refs,source_faces,parameters)
    outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,shape,solid).Solids())
    baseline_outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,shape,base).Solids())
    penetration=0.
    for p in native:
        for f in boolean(BRepAlgoAPI_Common,shape,p).Faces():
            n=p.normalAt();c=f.Center()
            if any(s.isInside(c+n*1e-5,1e-8) and s.isInside(c-n*1e-5,1e-8) for s in shape.Solids()):penetration+=f.Area()
    ratio=ratio_check(solid,base)
    gaps=[dict(panel_key=p['key'],minimum_distance_mm=f.distance(shape)) for p,f in zip(panels,native)]
    checks=[record('volume_ratio',ratio['passed'],ratio,'Fixed section exterior volume, not material volume','ratio',dict(minimum=1,maximum=1.2)),
            record('coverage',outside<=1e-6 and baseline_outside<=1e-6,dict(outside_volume_mm3=outside,baseline_outside_mm3=baseline_outside),'Native source difference for baseline and cover','mm3'),
            record('penetration',penetration<=1e-8,dict(material_crossing_area_mm2=penetration),'Independent face/interior crossing','mm2'),
            record('local_clearance',True,dict(panels=gaps,manufacturing_tolerance=None),'Measured native minimum distances; no manufacturing acceptance asserted','mm'),
            record('topology',solid.isValid() and all(f.isValid() for f in native),dict(manufacturing_faces=len(native),evaluation_caps=[n for n,_ in caps]),'Native solid and manufacturing surfaces checked separately'),
            record('unfolding',True,dict(state='requires_current_net'),'Foldback and seams must be checked on matching current blanket-net')]
    for c in checks:
        c['algorithm_version']=ALGORITHM
        if c['id']=='local_clearance':c.update(status='needs_review',reason='Native distances measured; manufacturing clearance limit is not approved')
        if c['id']=='unfolding':c.update(status='not_run',reason='No matching current net has been evaluated')
    lo,hi=bounds(solid)
    result=dict(schema_version=1,revision_id=revision,model_ref=copy.deepcopy(model.model_ref),parameters=copy.deepcopy(parameters),baseline=baseline,
                dimensions_mm=[b-a for a,b in zip(lo,hi)],panels=panels,native_shape_ref='manufacturing.brep',evaluation_shape_ref='evaluation.brep',
                display_ref='cover.glb',closures=[dict(id=n,shape_ref=f'closures/{i}.brep',evaluation_only=True) for i,(n,_) in enumerate(caps)],
                checks=checks,status='failed' if any(c['status']=='fail' for c in checks) else 'needs_review',candidate_editable=True,algorithm_version=ALGORITHM,
                downstream=dict(revision_id=revision,panels='candidates',unfolding='not_computed',checks_revision=revision))
    validate('blanket',result,'BlanketResult')
    if output is not None:
        output.mkdir(parents=True,exist_ok=True)
        for d in ['panels','closures']:(output/d).mkdir(exist_ok=True)
        frame.world(base).exportBrep(str(output/'baseline.brep'));frame.world(solid).exportBrep(str(output/'evaluation.brep'))
        cq.Compound.makeCompound([frame.world(f) for f in native]).exportBrep(str(output/'manufacturing.brep'))
        assembly=cq.Assembly()
        for p,f in zip(panels,native):
            f=frame.world(f);f.exportBrep(str(output/p['surface_ref']))
            assembly.add(f,name=p['id'].replace(':','_'),color=cq.Color(.75,.65,.25))
        for i,(_,f) in enumerate(caps):frame.world(f).exportBrep(str(output/f'closures/{i}.brep'))
        assembly.export(str(output/'cover.glb'))
        from .display import normalize
        normalize(output/'cover.glb',panels)
        (output/'blanket-result.json').write_text(canonical(result))
    return result
