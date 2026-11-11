"""Executed by the installed FreeCAD Python, not by the service environment."""
import json
import os
from pathlib import Path
import tempfile
import traceback

import FreeCAD as App
import Part
import importDWG

output = Path(os.environ['B04_CAD_OUTPUT'])
tempfile.tempdir = os.environ['B04_CAD_TEMP']
result = {'software':'FreeCAD','software_version':App.Version(),'status':'needs_review',
          'independent_native_dwg_parser':False,'conversion_backend':'ODA through installed FreeCAD importDWG.py',
          'autocad_acceptance':False,'steps':{},'limitations':[]}


def inventory(document):
    items=[]
    for obj in document.Objects:
        item={'name':obj.Name,'label':obj.Label,'type_id':obj.TypeId,'properties':obj.PropertiesList}
        if hasattr(obj,'Shape') and not obj.Shape.isNull():
            b=obj.Shape.BoundBox
            item.update(edges=len(obj.Shape.Edges),bounds=[b.XMin,b.YMin,b.XMax,b.YMax])
        if hasattr(obj,'Text'): item['text']=str(obj.Text)
        items.append(item)
    return items


try:
    params=App.ParamGet('User parameter:BaseApp/Preferences/Mod/Draft')
    params.SetString('TeighaFileConverter',os.environ['B04_ODA_EXECUTABLE'])
    params.SetBool('dxfUseLegacyImporter',False)
    params.SetBool('dxfUseLegacyExporter',False)
    params.SetBool('dxfImportTexts',True)
    params.SetBool('dxfImportLayouts',False)
    importDWG.open(os.environ['B04_CAD_INPUT'])
    document=App.ActiveDocument
    if document is None or not document.Objects:
        raise RuntimeError('FreeCAD did not import any objects')
    result['steps']['open']=True
    result['before']=inventory(document)
    candidates=[obj for obj in document.Objects if hasattr(obj,'Shape') and not obj.Shape.isNull()
                and len(obj.Shape.Edges)==4 and abs(obj.Shape.BoundBox.XLength-100)<1e-6
                and abs(obj.Shape.BoundBox.YLength-60)<1e-6]
    if not candidates:
        # The native FreeCAD importer splits LWPOLYLINE into individual edges.
        # Change the unambiguous left/bottom/top outer edges together; preserve closure.
        changes=[([0,0,100,0],[[-1,0],[100,0]]),([0,60,100,60],[[-1,60],[100,60]]),([0,0,0,60],[[-1,0],[-1,60]])]
        chosen=[]
        for bounds, points in changes:
            matches=[]
            for obj in document.Objects:
                if not hasattr(obj,'Shape') or obj.Shape.isNull() or len(obj.Shape.Edges)!=1:
                    continue
                b=obj.Shape.BoundBox
                if all(abs(a-c)<1e-6 for a,c in zip(bounds,[b.XMin,b.YMin,b.XMax,b.YMax])):
                    matches.append(obj)
            if len(matches)!=1:
                raise RuntimeError('Fragmented outline edge is ambiguous or absent')
            chosen.append((matches[0],points))
        for obj,points in chosen:
            obj.Shape=Part.makeLine(*[App.Vector(x,y,0) for x,y in points])
        result['contour_edit']={'object_names':[obj.Name for obj,_ in chosen], 'old_width_mm':100,'new_width_mm':101,
                                'method':'Move outer left edge x=0 to -1 and extend top/bottom; imported split segments remain closed'}
    elif len(candidates)!=1:
        raise RuntimeError('Multiple matching outlines; do not silently edit an arbitrary imported entity')
    else:
        contour=candidates[0]
        contour.Shape=Part.makePolygon([App.Vector(x,y,0) for x,y in ((0,0),(101,0),(101,60),(0,60),(0,0))])
        result['contour_edit']={'object_name':contour.Name,'old_width_mm':100,'new_width_mm':101}
    document.recompute()
    result['steps']['edit_contour']=True
    dimensions=[obj for obj in document.Objects if 'Dimension' in obj.TypeId or ('Start' in obj.PropertiesList and 'End' in obj.PropertiesList and 'Dimline' in obj.PropertiesList)]
    if dimensions:
        dim=dimensions[0]
        if 'Dimline' in dim.PropertiesList:
            old=dim.Dimline
            dim.Dimline=App.Vector(old.x,old.y-2,old.z)
            result['steps']['edit_dimension']=True
    if not result['steps'].get('edit_dimension'):
        result['steps']['edit_dimension']=False
        result['limitations'].append('Original editable DIMENSION semantics not exposed by FreeCAD native DXF import; no replacement dimension is fabricated.')
    document.recompute()
    document.saveAs(str(output/'edited.FCStd'))
    result['steps']['save_freecad']=True
    importDWG.export(list(document.Objects),str(output/'edited.dwg'))
    if not (output/'edited.dwg').is_file():
        raise RuntimeError('FreeCAD DWG export produced no file')
    result['steps']['save_dwg']=True
    App.closeDocument(document.Name)
    importDWG.open(str(output/'edited.dwg'))
    reopened=App.ActiveDocument
    result['after_reopen']=inventory(reopened)
    result['steps']['reopen_edited']=bool(reopened.Objects)
    result['steps']['edited_width_preserved']=any(abs(obj.Shape.BoundBox.XLength-101)<1e-6
        for obj in reopened.Objects if hasattr(obj,'Shape') and not obj.Shape.isNull())
    if not result['steps']['edited_width_preserved']:
        result['observed_contour_widths_mm']=[obj.Shape.BoundBox.XLength for obj in reopened.Objects
            if hasattr(obj,'Shape') and not obj.Shape.isNull() and obj.Shape.BoundBox.XLength>0]
        result['limitations'].append('Observed exported/reopened coordinates are 25.4 times the edited millimetres in this FreeCAD route.')
        raise RuntimeError('Edited contour width did not survive DWG export/reopen')
    App.closeDocument(reopened.Name)
    result['status']='partial_pass'
except Exception as exc:
    result['status']='unsupported_or_failed'
    result['error']=str(exc)
    result['traceback']=traceback.format_exc()
finally:
    (output/'freecad-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'freecad_result':result['status'],'steps':result['steps']}))
