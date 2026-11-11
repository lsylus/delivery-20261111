"""Readback artifacts reconstructed from the actual flattened domains and maps."""
import cadquery as cq
from .mapping import position3d
from .panels import world

def face(outer,holes,placement):
    def wire(points):return cq.Wire.makePolygon([cq.Vector(*placement(p)) for p in points],close=True)
    return cq.Face.makeFromWires(wire(outer),[wire(h) for h in holes])

def write(net,output):
    bodies=[];flat=[];tabs=[];ps={p['key']:p for p in net['panels']}
    for p in net['panels']:
        if p.get('surface_mapping'):
            native=cq.Shape.importBrep(str(output/p['surface_ref']))
            if not native.isValid():raise ValueError('invalid native source patch')
            bodies.append(native)
        else:bodies.append(face(p['net_outer'],p['net_holes'],lambda uv:position3d(p,uv)))
        flat.append(face(p['net_outer'],p['net_holes'],lambda uv:[*uv,0]))
    for t in net['overlaps']:
        target=ps[t['target_panel']]
        if target.get('surface_mapping'):
            from .surface_charts import native_face
            if target['surface_mapping']['kind']=='SPHERE':
                from .spherical_tabs import native_tab
                from .checks import boolean
                from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
                native,evidence=native_tab(target['surface_mapping'],t['receiving_uv'][:2],t['width_mm'])
                source=cq.Shape.importBrep(str(output/target['surface_ref']))
                outside=boolean(BRepAlgoAPI_Cut,native,source);area=sum(f.Area() for f in outside.Faces())
                if area>1e-6:raise ValueError('native spherical tab leaves receiving material')
                evidence['native_outside_receiving_area_mm2']=area
                t['surface_width_measurement'].update(evidence);tabs.append(native)
            else:tabs.append(native_face(target['surface_mapping'],t['receiving_uv']))
        else:tabs.append(face(t['receiving_uv'],[],lambda uv:world(target,uv)))
    cq.Compound.makeCompound(bodies).exportBrep(str(output/'folded-body.brep'))
    cq.Compound.makeCompound(flat).exportBrep(str(output/'flat-body.brep'))
    if tabs:cq.Compound.makeCompound(tabs).exportBrep(str(output/'folded-tabs.brep'))

    net['native_readback']={}
    for name in ['folded-body.brep','flat-body.brep','folded-tabs.brep']:
        if (output/name).exists():
            shape=cq.Shape.importBrep(str(output/name))
            if not shape.isValid():raise ValueError('invalid readback '+name)
            net['native_readback'][name]=dict(valid=True,faces=len(shape.Faces()),area_mm2=shape.Area(),surface_types=sorted(set(f.geomType() for f in shape.Faces())))
