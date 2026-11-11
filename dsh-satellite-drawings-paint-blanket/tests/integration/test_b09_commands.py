import sys,copy,json
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from thermal_drawings.paint.commands import validate_command
from thermal_drawings.domain.errors import ServiceError
from contracts import validate

@pytest.mark.parametrize('op,p',[
 ('drawing.export',{'result_id':'r','draft':False}),
 ('drawing.export',{'result_id':'r','draft':True,'path':'/tmp/stolen'}),
 ('drawing.edit_annotation',{'result_id':'r','annotation_id':'a','text':'two\nlines','position':[0,0]}),
 ('history.undo',{'target':'foreign'}),
 ('paint.edit_regions',{'result_id':'r','action':'add','reason':'x','points':[[0,0],[1,0],[2,0]]}),
 ('paint.edit_regions',{'result_id':'r','action':'move','reason':'x','region_id':'x','delta_mm':[float('inf'),0]}),
])
def test_bounded_validator_rejects_unsafe_or_ambiguous_commands(op,p):
 with pytest.raises(ServiceError):validate_command(op,p)

def test_contract_and_runtime_schema_copies_remain_equal():
 root=Path(__file__).resolve().parents[2]
 for name in ('operation','runtime','paint','model','common'):
  assert (root/f'contracts/{name}.schema.json').read_bytes()==(root/f'service/src/thermal_drawings/domain/schemas/{name}.schema.json').read_bytes()

def test_manual_protection_clips_holes_and_does_not_double_cover_material():
 from thermal_drawings.paint.commands import prepare_edit
 from thermal_drawings.drawing.document_edits import apply_edits,geometry
 from shapely.geometry import Polygon
 from shapely.ops import unary_union
 root=Path(__file__).resolve().parents[2]
 paint=json.loads((root/'docs/evidence/B08/artifacts/paint-result.json').read_text())
 doc=paint['drawing_document'];frame=doc['frame']
 refs=next(e['source_refs'] for e in doc['entities'] if e['layer']=='OUTLINE')
 rev=dict(id=paint['revision_id'],model_ref=paint['model_ref'],selection=refs,document_edits=[])
 # Entire selected plane plus margin: actual voids must remain unfilled.
 pts=[[-200,-200],[200,-200],[200,200],[-200,200]]
 rev['document_edits']=[prepare_edit('paint.edit_regions',dict(result_id='oracle',action='add',points=pts,reason='explicit plane protection'),paint,rev)]
 changed=apply_edits(paint,rev)
 outlines=[e['points'] for e in doc['entities'] if e['layer']=='OUTLINE']
 material=Polygon()
 for points in outlines:
  area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
  if area>0:material=material.union(Polygon(points))
 for points in outlines:
  area=sum(a[0]*b[1]-a[1]*b[0] for a,b in zip(points,points[1:]+points[:1]))
  if area<0:material=material.difference(Polygon(points))
 shapes=[geometry(r['loops']) for r in changed['regions'] if r['local_frame']==frame]
 assert material.symmetric_difference(unary_union(shapes)).area<1e-6
 assert abs(sum(p.area for p in shapes)-unary_union(shapes).area)<1e-6
 assert any(len(r['loops'])>1 for r in changed['regions'])
 assert paint==json.loads((root/'docs/evidence/B08/artifacts/paint-result.json').read_text())

def test_annotation_move_keeps_protection_and_single_editable_text():
 from thermal_drawings.paint.commands import prepare_edit
 from thermal_drawings.drawing.document_edits import apply_edits
 root=Path(__file__).resolve().parents[2]
 paint=json.loads((root/'docs/evidence/B08/artifacts/paint-result.json').read_text())
 refs=next(e['source_refs'] for e in paint['drawing_document']['entities'] if e['layer']=='OUTLINE')
 rev=dict(id=paint['revision_id'],model_ref=paint['model_ref'],selection=refs,document_edits=[])
 for position in ([0,0],[5,8]):
  rev['document_edits'].append(prepare_edit('drawing.edit_annotation',dict(result_id='oracle',annotation_id='note',text='move note',position=position),paint,rev))
 changed=apply_edits(paint,rev)
 assert changed['regions']==paint['regions'] and changed['overlay']==paint['overlay']
 text=[e for e in changed['drawing_document']['entities'] if e['kind']=='text']
 assert len(text)==1 and text[0]['position']==[5,8] and text[0]['text']=='move note'
