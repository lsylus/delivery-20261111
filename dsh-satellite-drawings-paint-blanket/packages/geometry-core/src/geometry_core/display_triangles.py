"""Strict display triangle payloads with one native remesh recovery attempt.

Native faces and manufacturing topology are never removed or repaired here.
"""
import numpy as np
from OCP.BRepTools import BRepTools
from OCP.BRepMesh import BRepMesh_IncrementalMesh


def triangle_payload(points, triangles):
    """Preserve source triangle order and exact-duplicate collapse evidence."""
    coordinates=np.asarray([point.toTuple() for point in points],dtype=np.float64)
    indices=np.asarray(triangles,dtype=np.int64)
    if not np.isfinite(coordinates).all():
        raise ValueError('non-finite tessellation position')
    xyz=coordinates[indices]
    cross=np.cross(xyz[:,1]-xyz[:,0],xyz[:,2]-xyz[:,0])
    norms=np.linalg.norm(cross,axis=1)
    if not np.isfinite(norms).all():
        raise ValueError('non-finite tessellation normal')
    tiny=norms<=1e-15
    repeated=np.all(xyz[:,0]==xyz[:,1],axis=1)|np.all(xyz[:,0]==xyz[:,2],axis=1)|np.all(xyz[:,1]==xyz[:,2],axis=1)
    if np.any(tiny&((norms!=0)|~repeated)):
        raise ValueError('degenerate tessellation triangle')
    collapsed=[dict(source_triangle=int(i),node_ids=indices[i].tolist(),points_mm=xyz[i].tolist(),twice_area_mm2=float(norms[i]),reason='exact_duplicate_coordinates') for i in np.flatnonzero(tiny)]
    keep=~tiny;emitted=np.flatnonzero(keep).tolist()
    positions=xyz[keep].reshape((-1,3))
    normals=np.repeat(cross[keep]/norms[keep,None],3,axis=0)
    return positions,normals,collapsed,emitted,float(np.sum(norms[keep])/2)


def _checked_payload(face, points, triangles):
    if not triangles:
        raise ValueError('face has no triangles; refusing incomplete display map')
    payload=triangle_payload(points,triangles)
    if not payload[3]:
        raise ValueError('face has no nondegenerate triangles; refusing incomplete display map')
    if payload[2] and not face.isValid():
        raise ValueError('invalid native face with collapsed display triangles')
    return payload


def tessellate_face(face, tolerance_mm, angular_tolerance, *, relative=True):
    """Return five strict payload values and native meshing diagnostics.

    ``relative`` records the caller's existing mesh mode; it does not remesh.
    Only original empty/degenerate payload errors admit a single retry on a
    valid native face. Invalid empty faces remain available for strict catalog
    classification by the caller.
    Retry triangulates a private topology copy at absolute 0.1mm / 0.35rad.
    It is checked by exactly the same triangle rules as the initial result.
    """
    points,triangles=face.tessellate(tolerance_mm,angular_tolerance)
    initial=dict(linear_deflection_mm=tolerance_mm,angular_deflection_rad=angular_tolerance,relative=relative)
    diagnostic=dict(remeshed=False,reason=None,initial=initial,effective=initial.copy(),
                    source_triangles=len(triangles),initial_source_triangles=len(triangles),
                    maximum_tolerance_mm=tolerance_mm,maximum_angular_tolerance_rad=angular_tolerance)
    try:
        payload=_checked_payload(face,points,triangles)
    except ValueError as error:
        empty_error='face has no triangles; refusing incomplete display map'
        is_empty=str(error)==empty_error
        if not is_empty and str(error)!='degenerate tessellation triangle':
            raise
        if not face.isValid():
            if is_empty:
                raise
            raise ValueError('invalid native face with degenerate display triangles') from error
        retry=face.copy(mesh=False)
        BRepTools.Clean_s(retry.wrapped)
        mesher=BRepMesh_IncrementalMesh(retry.wrapped,0.1,False,0.35,False)
        if not mesher.IsDone():
            raise ValueError('native display remesh failed') from error
        # Equal tolerances retain this absolute native mesh in CadQuery's cache.
        points,triangles=retry.tessellate(0.1,0.35)
        payload=_checked_payload(retry,points,triangles)
        diagnostic.update(remeshed=True,reason='initial_empty_tessellation' if is_empty else 'initial_degenerate_tessellation_triangle',
                          effective=dict(linear_deflection_mm=0.1,angular_deflection_rad=0.35,relative=False),
                          source_triangles=len(triangles),maximum_tolerance_mm=max(tolerance_mm,0.1),
                          maximum_angular_tolerance_rad=max(angular_tolerance,0.35))
    return (*payload,diagnostic)


def classify_unrenderable_face(face):
    """Catalog only empty, zero-measure planar line loops; retain native CAD.

    No triangulation, repair, tolerance change, or source-shape mutation occurs.
    A returned record permits an explicit display catalog entry, never a
    manufacturing validity override. Other unrenderable faces remain failures.
    """
    import math
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    try:
        triangulation=BRep_Tool.Triangulation_s(face.wrapped,TopLoc_Location())
        if triangulation is not None and triangulation.NbTriangles()>0:
            return None
        if face.geomType()!='PLANE':
            return None
        edges=face.Edges()
        if len(edges)!=2 or any(edge.geomType()!='LINE' for edge in edges):
            return None
        area=float(face.Area());uv=[float(v) for v in face._uvBounds()]
        if (len(uv)!=4 or not all(math.isfinite(v) for v in [area,*uv])
                or not all(math.isfinite(edge.Length()) for edge in edges)):
            return None
        if abs(area)>1e-9 or uv[1]<uv[0] or uv[3]<uv[2]:
            return None
        # Planar U/V axes are arbitrary: diagonal collapsed loops can have two
        # nonzero axis-aligned UV spans. Check the actual line endpoints in mm.
        endpoints=np.asarray([point.toTuple() for edge in edges
                              for point in (edge.startPoint(),edge.endPoint())],dtype=np.float64)
        if endpoints.shape!=(4,3) or not np.isfinite(endpoints).all():
            return None
        differences=endpoints[:,None,:]-endpoints[None,:,:]
        distances=np.linalg.norm(differences,axis=2)
        if not np.isfinite(distances).all():
            return None
        first,last=np.unravel_index(np.argmax(distances),distances.shape)
        diameter=float(distances[first,last])
        origin=endpoints[first]
        if diameter<=1e-7:
            direction=None
            maximum_distance=diameter
        else:
            direction=(endpoints[last]-origin)/diameter
            orthogonal_distances=np.linalg.norm(np.cross(endpoints-origin,direction),axis=1)
            if not np.isfinite(orthogonal_distances).all():
                return None
            maximum_distance=float(np.max(orthogonal_distances))
            if maximum_distance>1e-7:
                return None
        return dict(reason='zero_measure_planar_face',native_valid=bool(face.isValid()),
                    native_area_mm2=area,uv_bounds=uv,edge_count=len(edges),
                    endpoint_diameter_mm=diameter,maximum_endpoint_line_distance_mm=maximum_distance,
                    common_line_origin_mm=origin.tolist(),
                    common_line_direction=None if direction is None else direction.tolist(),
                    threshold=dict(maximum_absolute_area_mm2=1e-9,maximum_endpoint_line_distance_mm=1e-7),
                    native_retained=True,source_triangles=0)
    except Exception:
        # Invalid or unsupported measurement is not evidence of zero measure.
        return None
