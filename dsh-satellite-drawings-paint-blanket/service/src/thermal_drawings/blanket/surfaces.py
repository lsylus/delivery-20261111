"""Five planar manufacturing candidates and independent closure faces."""
import cadquery as cq
from .openings import cut_openings, face
from .selection import BlanketError

SIDES=('x-','x+','y-','y+','z+')


def build(parameters,baseline,dims,selected,revision):
    x,y,z=dims;cx,cy,_=baseline['parameters']['bottom_center_mm'];xmin=cx-x/2;ymin=cy-y/2
    # Each local UV frame is right-handed and points outwards.
    specs={
        'x-':([xmin,ymin,0],[0,0,1],[0,1,0],z,y),
        'x+':([xmin+x,ymin,0],[0,1,0],[0,0,1],y,z),
        'y-':([xmin,ymin,0],[1,0,0],[0,0,1],x,z),
        'y+':([xmin,ymin+y,0],[0,0,1],[1,0,0],z,x),
        'z+':([xmin,ymin,z],[1,0,0],[0,1,0],x,y)}
    panels=[];native=[];caps=[]
    ids=[o['id'] for o in parameters['openings']]
    if len(ids)!=len(set(ids)):
        raise BlanketError('duplicate opening ID')
    if any(o['panel'] not in SIDES for o in parameters['openings']):
        raise BlanketError('invalid opening panel')
    for side,(origin,u,v,w,h) in specs.items():
        def placement(p):
            return [origin[i]+u[i]*p[0]+v[i]*p[1] for i in range(3)]
        openings=[o for o in parameters['openings'] if o['panel']==side]
        ref=selected['source_refs'][side]
        excluded=ref in parameters['excluded_faces'] or bool(parameters['included_faces'] and ref not in parameters['included_faces'])
        if excluded:
            if openings:
                raise BlanketError('opening on excluded panel')
            caps.append((f'excluded:{side}',face([[0,0],[w,0],[w,h],[0,h]],placement)))
            continue
        shape,closures,holes=cut_openings(w,h,openings,placement)
        native.append(shape);caps.extend(closures)
        normal=cq.Vector(*u).cross(cq.Vector(*v)).toTuple()
        f=selected['frame'];world_origin=f.point(origin)
        def direction(a):
            p=f.point([origin[i]+a[i] for i in range(3)])
            return [p[i]-world_origin[i] for i in range(3)]
        panels.append(dict(id=f'{revision}:{side}',side=side,surface_ref=f'panels/{side}.brep',
                           outer_loop=dict(points=[[0,0],[w,0],[w,h],[0,h]],closed=True,orientation='ccw'),holes=holes,
                           frame=dict(origin=world_origin,x_axis=direction(u),y_axis=direction(v),z_axis=direction(normal),units='mm',handedness='right'),
                           source_refs=[ref],mapping_ref=f'{revision}:{side}:planar-uv'))
    if not native:
        raise BlanketError('empty manufacturing cover')
    caps.append(('installation-bottom',face([[xmin,ymin,0],[xmin,ymin+y,0],[xmin+x,ymin+y,0],[xmin+x,ymin,0]],lambda p:p)))
    return panels,native,caps
