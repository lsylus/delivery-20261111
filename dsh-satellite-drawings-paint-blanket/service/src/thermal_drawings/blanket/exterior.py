"""Native exterior closure of bounded recess mouths; no bounding-box surrogate."""
import cadquery as cq
from ..paint.curved_targets import feature_inventory
from .selection import BlanketError
from .checks import boolean
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut

def close_recesses(source):
    if not source.isValid() or len(source.Solids())!=1:raise BlanketError('invalid_exterior_source')
    solid=source.Solids()[0]
    outer=cq.Solid.makeSolid(solid.outerShell())
    faces=outer.Faces()
    inventory=feature_inventory(outer)
    mouths=[m for m in inventory if m['candidate']=='recess_or_hole']
    cap_targets={m['target_face'] for m in mouths}
    adjacency={i:[] for i in range(len(faces))}
    for i,a in enumerate(faces):
        for j in range(i):
            if any(e.isSame(f) for e in a.Edges() for f in faces[j].Edges()):
                adjacency[i].append(j);adjacency[j].append(i)
    removed=set();queue=[i for m in mouths for i in m['adjacent_faces']]
    for i in queue:
        if i in removed or i in cap_targets:continue
        removed.add(i)
        queue.extend(j for j in adjacency[i] if j not in removed and j not in cap_targets)
        if len(queue)>len(faces)*len(faces)+1:raise BlanketError('closure_graph_budget')
    retained=[]
    for i,f in enumerate(faces):
        if i in removed:continue
        if i in cap_targets:
            # Only the approved topology candidates are closed; boss loops stay.
            closed={int(m['id'].rsplit('-',1)[1]) for m in mouths if m['target_face']==i}
            holes=[w for j,w in enumerate(f.innerWires()) if j not in closed]
            retained.append(cq.Face.makeFromWires(f.outerWire(),holes))
        else:retained.append(f)
    try:
        shell=cq.Shell.makeShell(retained);result=cq.Solid.makeSolid(shell)
        if result.Volume()<0:result=cq.Solid(result.wrapped.Reversed())
        if not result.isValid():raise ValueError('invalid closed shell')
        outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,source,result).Solids())
        if outside>1e-6:raise ValueError('source escapes closure')
    except Exception as e:raise BlanketError('native_recess_closure_needs_review: '+str(e)) from e
    return result,dict(algorithm='b13-native-recess-closure-v1',material_volume_mm3=source.Volume(),
                       exterior_volume_mm3=result.Volume(),closed_mouths=mouths,removed_interior_face_indices=sorted(removed),
                       source_outside_volume_mm3=outside,closure_policy='close bounded inward mouths; preserve outward bosses and unbounded exterior concavities',
                       engineering_approval='pending')

def scaled_candidate(source,factor=1.01):
    """Uniform scale from a fixed installation anchor; native containment decides validity."""
    import math
    if not math.isfinite(factor) or not 1<=factor<=2:raise BlanketError('invalid_scale')
    baseline,closure=close_recesses(source)
    b=baseline.BoundingBox();anchor=cq.Vector((b.xmin+b.xmax)/2,(b.ymin+b.ymax)/2,b.zmin)
    cover=baseline.translate(-anchor).scale(factor).translate(anchor)
    outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,source,cover).Solids())
    return baseline,cover,dict(closure=closure,scale=factor,anchor_mm=list(anchor.toTuple()),baseline_volume_mm3=baseline.Volume(),
        cover_volume_mm3=cover.Volume(),ratio=cover.Volume()/baseline.Volume(),outside_volume_mm3=outside,
        containment='pass' if outside<=1e-6 else 'fail',ratio_check='pass' if 1<=cover.Volume()/baseline.Volume()<=1.2 else 'fail',
        status='measured',manufacturing_tolerance=None)

def offset_candidate(source,clearance_mm=1.0):
    """True native parallel offset, clipped to a fixed installation bottom."""
    import math
    from OCP.BRepOffsetAPI import BRepOffsetAPI_MakeOffsetShape
    from OCP.BRepOffset import BRepOffset_Skin
    from OCP.GeomAbs import GeomAbs_Arc
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from ..domain.validation import fingerprint
    from .selection import shape_hash
    if not math.isfinite(clearance_mm) or not 0<clearance_mm<=50:raise BlanketError('invalid_offset')
    baseline,closure=close_recesses(source)
    op=BRepOffsetAPI_MakeOffsetShape()
    op.PerformByJoin(baseline.wrapped,clearance_mm,1e-6,BRepOffset_Skin,False,False,GeomAbs_Arc,True)
    if not op.IsDone():raise BlanketError('native_offset_incomplete')
    raw=cq.Shape.cast(op.Shape());b=baseline.BoundingBox();c=raw.BoundingBox()
    clip=cq.Solid.makeBox(c.xlen+2,c.ylen+2,c.zmax-b.zmin+1,cq.Vector(c.xmin-1,c.ymin-1,b.zmin))
    cover=boolean(BRepAlgoAPI_Common,raw,clip)
    if not cover.isValid() or len(cover.Solids())!=1:raise BlanketError('invalid_native_offset')
    outside=sum(s.Volume() for s in boolean(BRepAlgoAPI_Cut,source,cover).Solids())
    caps=[];material=[];gaps=[];crossings=0.
    for i,f in enumerate(cover.Faces()):
        if f.geomType()=='PLANE' and abs(f.Center().z-b.zmin)<1e-6 and abs(f.normalAt().z)>.999:
            caps.append(f);continue
        material.append(f)
        try:gaps.append(dict(face=i,distance_mm=f.distance(source),method='native_minimum'))
        except Exception as error:
            # Preserve the native solver failure and a separately labelled
            # sampled upper estimate. It cannot establish a minimum clearance.
            samples=[]
            for vertex in f.Vertices():
                try:samples.append(vertex.distance(source))
                except Exception:pass
            gaps.append(dict(face=i,distance_mm=None,method='native_failed',error=type(error).__name__,
                             face_area_mm2=f.Area(),sampled_vertex_minimum_mm=min(samples) if samples else None,interval=clearance_interval(f,source)))
        for part in boolean(BRepAlgoAPI_Common,source,f).Faces():
            p=part.Center();n=f.normalAt()
            if any(s.isInside(p+n*1e-5,1e-8) and s.isInside(p-n*1e-5,1e-8) for s in source.Solids()):crossings+=part.Area()
    ratio=cover.Volume()/baseline.Volume()
    record=dict(schema_version=1,algorithm_version='b13-native-offset-v1',
        baseline=dict(id='baseline-'+fingerprint(dict(source_hash=shape_hash(source),algorithm=closure['algorithm'],closure_policy=closure['closure_policy'])),
                      algorithm=closure['algorithm'],volume_mm3=baseline.Volume(),closure=closure),
        clearance_mm=clearance_mm,cover_volume_mm3=cover.Volume(),volume_ratio=ratio,
        checks=dict(containment=dict(status='pass' if outside<=1e-6 else 'fail',outside_volume_mm3=outside),
                    penetration=dict(status='pass' if crossings<=1e-8 else 'fail',crossing_area_mm2=crossings),
                    ratio=dict(status='pass' if 1<=ratio<=1.2 else 'fail',minimum=1,maximum=1.2),
                    local_clearance=dict(status='measured',faces=gaps,manufacturing_tolerance=None)),
        evaluation_only_caps=len(caps),manufacturing_faces=len(material),status='needs_review',
        blockers=['case-specific opening and clearance approval','curved multi-panel seam/overlap and manufacturing error approval'])
    return baseline,cover,cq.Compound.makeCompound(material),record

def clearance_interval(face,source,subdivisions=4):
    """Conservative UV-rectangle lower bound and actual-vertex upper bound.

    Every trimmed patch lies inside its underlying parameter rectangle. For a
    native sample q and any x in its geometry bounding box, distance(x,source)
    >= distance(q,source)-|x-q|. This remains a bound when q is outside the trim.
    No sampled minimum is mislabeled as the exact minimum.
    """
    import math
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    surface=BRep_Tool.Surface_s(face.wrapped);adaptor=BRepAdaptor_Surface(face.wrapped)
    u0,u1,v0,v1=face._uvBounds();lower=[];upper=[];failed=0
    for v in face.Vertices():
        try:upper.append(v.distance(source))
        except Exception:pass
    us=np.linspace(u0,u1,subdivisions+1);vs=np.linspace(v0,v1,subdivisions+1)
    for ua,ub in zip(us,us[1:]):
        for va,vb in zip(vs,vs[1:]):
            try:
                patch=BRepBuilderAPI_MakeFace(surface,float(ua),float(ub),float(va),float(vb),1e-7).Face()
                bbox=Bnd_Box();BRepBndLib.AddOptimal_s(patch,bbox,False,True)
                xyz=bbox.Get();p=adaptor.Value((ua+ub)/2,(va+vb)/2);q=[p.X(),p.Y(),p.Z()]
                radius=math.sqrt(sum(max(abs(q[i]-xyz[i]),abs(q[i]-xyz[i+3]))**2 for i in range(3)))+1e-6
                dist=cq.Vertex.makeVertex(*q).distance(source)
                lower.append(max(0.,dist-radius))
            except Exception:
                lower.append(0.);failed+=1
    return dict(minimum_distance_interval_mm=[min(lower,default=0.),min(upper) if upper else None],
                patches=subdivisions**2,failed_patches=failed,method='native_uv_rectangle_bbox_interval',
                definition='Native point distance minus conservative geometric patch-box radius; actual source-face vertices provide upper bound; 1e-6mm numerical inflation, not manufacturing tolerance')
