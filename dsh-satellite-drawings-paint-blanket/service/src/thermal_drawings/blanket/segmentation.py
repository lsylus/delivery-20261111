"""Piecewise triangle charts with measured native surface deviation.

Each chord triangle is isometric; the entire curved surface explicitly is not.
Surface-vs-chord strain and shape deviation remain reported, never rounded away.
"""
import math
import numpy as np
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from .panels import NetError
from .developable import Developable

def piecewise(face,deflection_mm=0.5,angular_tolerance=0.2,maximum_triangles=12000):
    if not math.isfinite(deflection_mm) or not 1e-5<=deflection_mm<=100 or not 0.01<=angular_tolerance<=0.5:
        raise NetError('invalid_piecewise_resolution')
    # Work on a BRep copy to avoid reusing a coarse triangulation from an earlier run.
    import io
    stream=io.BytesIO();face.exportBrep(stream);stream.seek(0)
    local=cq.Shape.importBrep(stream).Faces()[0]
    points,indices=local.tessellate(deflection_mm,angular_tolerance)
    if not indices or len(indices)>maximum_triangles:raise NetError('piecewise_triangle_budget')
    surf=BRepAdaptor_Surface(local.wrapped);charts=[];max_chord=0.;max_strain=0.;max_dev=0.
    for i,ids in enumerate(indices):
        xyz=np.array([points[j].toTuple() for j in ids]);a,b,c=xyz
        ab=np.linalg.norm(b-a)
        if ab<1e-12:continue
        x=(b-a)/ab;normal=np.cross(b-a,c-a);norm=np.linalg.norm(normal)
        if norm<1e-12:continue
        normal/=norm;y=np.cross(normal,x)
        xy=np.array([[0.,0.],[ab,0.],[np.dot(c-a,x),np.dot(c-a,y)]])
        edge_errors=[];surface_errors=[];deviations=[]
        for j,k in [(0,1),(1,2),(2,0)]:
            chord=float(np.linalg.norm(xyz[k]-xyz[j]));flat=float(np.linalg.norm(xy[k]-xy[j]))
            edge_errors.append(abs(flat-chord))
            # Project chord samples onto the actual trimmed native face. This
            # approximates the surface path; it is not claimed to be a geodesic.
            samples=[]
            for t in np.linspace(0,1,9):
                p=xyz[j]*(1-t)+xyz[k]*t
                uv=local.paramAt(cq.Vector(*p));q=surf.Value(*uv)
                samples.append(np.array([q.X(),q.Y(),q.Z()]))
                deviations.append(float(np.linalg.norm(samples[-1]-p)))
            arc=sum(float(np.linalg.norm(q-p)) for p,q in zip(samples,samples[1:]))
            surface_errors.append((arc-chord)/arc if arc>0 else 0.)
        center=xyz.mean(axis=0);uv=local.paramAt(cq.Vector(*center));q=surf.Value(*uv)
        deviations.append(float(np.linalg.norm(np.array([q.X(),q.Y(),q.Z()])-center)))
        chord_error=max(edge_errors);strain=max(map(abs,surface_errors));dev=max(deviations)
        max_chord=max(max_chord,chord_error);max_strain=max(max_strain,strain);max_dev=max(max_dev,dev)
        charts.append(dict(key=f'triangle-{i}',vertex_indices=list(ids),world_vertices=xyz.tolist(),flat_vertices=xy.tolist(),
                           maximum_chord_edge_error_mm=chord_error,maximum_surface_chord_strain=strain,maximum_sampled_deviation_mm=dev))
    if not charts:raise NetError('empty_piecewise_mapping')
    return dict(schema_version=1,algorithm_version='b13-piecewise-v1',mapping_type='piecewise',surface_type=face.geomType(),
                deflection_request_mm=deflection_mm,triangles=charts,triangle_count=len(charts),
                maximum_chord_edge_error_mm=max_chord,maximum_surface_chord_strain=max_strain,maximum_sampled_deviation_mm=max_dev,
                measurement='Chord-edge reconstruction; 9 projected edge samples plus centroid per triangle; maxima are sampled, not certified global Hausdorff bounds.',
                manufacturing_tolerance=None,status='blocked',blocker='case-specific manufacturing strain/deviation and seam plan approval missing')
