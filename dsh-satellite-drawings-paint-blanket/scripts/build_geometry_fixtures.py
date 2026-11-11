"""Generate small real OCCT fixtures; no business algorithms or holdout inputs."""
import argparse, hashlib, json, re
from pathlib import Path
import cadquery as cq
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.TopLoc import TopLoc_Location

def named(label,name):
    TDataStd_Name.Set_s(label,TCollection_ExtendedString(name)); return label

def stable_header(path):
    # Only header timestamp is normalized; no geometry payload is modified.
    raw=path.read_bytes()
    raw=re.sub(rb"'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d'",b"'2026-11-07T00:00:00'",raw,count=1)
    path.write_bytes(raw)

def write_doc(doc,path):
    writer=STEPCAFControl_Writer(); writer.SetNameMode(True)
    assert writer.Transfer(doc,STEPControl_AsIs)
    assert writer.Write(str(path))==IFSelect_RetDone
    stable_header(path)

def build(output):
    output.mkdir(parents=True,exist_ok=True)
    doc=TDocStd_Document(TCollection_ExtendedString('fixtures'))
    st=XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    box=cq.Solid.makeBox(10,20,30)
    definition=named(st.AddShape(box.wrapped,False),'shared-box')
    nested=named(st.NewShape(),'nested')
    named(st.AddComponent(nested,definition,cq.Location((5,0,0)).wrapped),'left-foot')
    named(st.AddComponent(nested,definition,cq.Location((25,0,0),(0,0,1),90).wrapped),'right-foot')
    root=named(st.NewShape(),'assembly-root')
    named(st.AddComponent(root,nested,cq.Location((100,50,10),(0,0,1),90).wrapped),'nested-rotated')
    sheet=cq.Face.makeFromWires(cq.Wire.makePolygon([(0,0,0),(8,0,0),(8,4,0),(0,4,0)],close=True))
    mixed=cq.Compound.makeCompound([cq.Solid.makeBox(2,3,0.01),sheet.translate((0,0,7))])
    named(st.AddShape(mixed.wrapped,False),'thin-and-sheet')
    st.UpdateAssemblies(); write_doc(doc,output/'assembly-tree.step')
    shapes={'box-100':cq.Solid.makeBox(100,100,100),
            'concave':cq.Workplane('XY').polyline([(0,0),(20,0),(20,5),(5,5),(5,20),(0,20)]).close().extrude(3).val()}
    outer=cq.Wire.makePolygon([(0,0,0),(100,0,0),(100,80,0),(0,80,0)],close=True)
    inner=cq.Wire.makePolygon([(40,30,0),(60,30,0),(60,50,0),(40,50,0)],close=True)
    shapes['panel-opening']=cq.Face.makeFromWires(outer,[inner])
    plate=cq.Solid.makeBox(100,80,5,cq.Vector(-50,-40,0)).cut(cq.Solid.makeCylinder(3,5,cq.Vector(0,0,0)))
    boss=cq.Solid.makeCylinder(4,4,cq.Vector(0,20,5))
    rib=cq.Solid.makeBox(2,20,4,cq.Vector(-1,-30,5))
    for gap in (0,0.099,0.1,0.101):
        feet=[cq.Solid.makeBox(10,10,4,cq.Vector(x-5,-5,5+gap)) for x in (-20,20)]
        shapes[f'paint-plate-{gap:g}']=cq.Compound.makeCompound([plate,boss,rib,*feet])
    for name,shape in shapes.items():
        path=output/f'{name}.step'; cq.exporters.export(shape,str(path)); stable_header(path)
    # A non-mm file verifies explicit reader normalization, not a suffix claim.
    Interface_Static.SetCVal_s('write.step.unit','INCH')
    try:
        path=output/'inch-box.step'; cq.Solid.makeBox(25.4,50.8,76.2).exportStep(str(path),unit='MM',outputUnit='INCH'); stable_header(path)
    finally: Interface_Static.SetCVal_s('write.step.unit','MM')
    manifest={'schema_version':1,'stage':'generated_OCCT_B02','oracle':{'length_absolute_mm':1e-6,'area_volume_relative':1e-6,'zero_absolute':1e-9},'files':[]}
    for path in sorted(output.glob('*.step')):
        manifest['files'].append({'path':path.name,'bytes':path.stat().st_size,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    (output/'geometry-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output),indent=2))
