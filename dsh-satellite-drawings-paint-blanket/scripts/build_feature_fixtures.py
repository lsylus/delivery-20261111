"""A named equipment subassembly with an unrelated neighbour for scope checks."""
import hashlib
import json
from pathlib import Path
import cadquery as cq
from cadquery.occ_impl.assembly import toCAF
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence
from OCP.XCAFDoc import XCAFDoc_DocumentTool


def save_named_assembly(assembly, path):
    # CadQuery names assembly definitions but omits subassembly occurrences.
    # Give each occurrence its definition name so this fixture models a named
    # equipment module, rather than relying on a reader-specific fallback.
    root, doc = toCAF(assembly, True)
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    def name_components(parent):
        children = TDF_LabelSequence()
        tool.GetComponents_s(parent, children)
        for index in range(1, children.Length() + 1):
            child = children.Value(index)
            definition = TDF_Label()
            if tool.GetReferredShape_s(child, definition):
                name = TDataStd_Name()
                if definition.FindAttribute(TDataStd_Name.GetID_s(), name):
                    TDataStd_Name.Set_s(child, TCollection_ExtendedString(name.Get().ToExtString()))
                if tool.IsAssembly_s(definition):
                    name_components(definition)

    name_components(root)
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetLayerMode(True)
    writer.SetNameMode(True)
    if not writer.Transfer(doc, STEPControl_AsIs):
        raise RuntimeError('fixture STEP transfer failed')
    if writer.Write(str(path)) != IFSelect_RetDone:
        raise RuntimeError('fixture STEP write failed')

ROOT=Path(__file__).resolve().parents[1]


def build():
    output=ROOT/'fixtures/synthetic/feature-composite'
    output.mkdir(parents=True,exist_ok=True)
    equipment=cq.Assembly(name='Equipment-module')
    equipment.add(cq.Solid.makeBox(100,100,100,cq.Vector(-50,-50,0)),name='Body')
    equipment.add(cq.Solid.makeCylinder(10,40,cq.Vector(0,0,100)),name='Terminal')
    assembly=cq.Assembly(name='Satellite-example')
    assembly.add(equipment)
    assembly.add(cq.Solid.makeBox(30,30,50,cq.Vector(170,-15,0)),name='Unrelated-device')
    path=output/'cube-cylinder-module.step'
    save_named_assembly(assembly, path)
    manifest=dict(purpose='Click equipment once to include its body and terminal, excluding neighbouring equipment.',
                  case='cube-cylinder-module',source=str(path.relative_to(ROOT)),units='mm',
                  sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,
                  equipment_name='Equipment-module',included_members=['Body','Terminal'],
                  unrelated_members=['Unrelated-device'],default_excluded_instances=[])
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':build()
