"""Static geometry evidence for full-width corner conflict and selectable alternatives."""
import copy,json,sys,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from shapely.geometry import shape
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/blanket'))
from net_helpers import cover,cut_settings
from thermal_drawings.blanket.net_pipeline import generate_net
from thermal_drawings.blanket.seams import adjacency
out=ROOT/'docs/evidence/B11/previews';out.mkdir(parents=True,exist_ok=True)
c=cover();settings=cut_settings(c);edges,seams=adjacency(c['panels']);settings['seam_overrides']=[]
for seam in seams:
    a,b=[edges[seam[k]]['panel'] for k in ('edge_a','edge_b')]
    if 'z+' in (a,b) and ('x+' in (a,b) or 'y+' in (a,b)):
        settings['seam_overrides'].append(dict(id=seam['id'],kind='join',overlap_owner_panel=a if a!='z+' else b,width_mm=15))
conflict=generate_net(c,settings);assert conflict['status']=='failed'
diagnostic=next(d for d in conflict['diagnostics'] if d['code']=='folded_corner_collision')
cases=[('Original: corner collision',conflict)]
for i,candidate in enumerate(diagnostic['candidates'],1):
    changed=copy.deepcopy(settings)
    for edit in changed['seam_overrides']:
        if edit['id']==candidate['seam_id']:edit['overlap_owner_panel']=candidate['panel_key']
    alternative=generate_net(c,changed);assert alternative['status']=='passed'
    assert all(t['width_mm']==15 for t in alternative['overlaps']) and alternative['cover_checks']==conflict['cover_checks']
    cases.append((f'Choice {i}: switch one owner',alternative))
canvas=Image.new('RGB',(1110,470),'#f5f7fa');draw=ImageDraw.Draw(canvas,'RGBA')
try:font=ImageFont.truetype('DejaVuSans.ttf',18);small=ImageFont.truetype('DejaVuSans.ttf',14)
except OSError:font=small=ImageFont.load_default()
for i,(label,net) in enumerate(cases):
    ox=30+i*370;oy=390;scale=2.8
    def pt(p):return (ox+p[0]*scale,oy-p[1]*scale)
    draw.text((ox,20),label,font=font,fill='#172033')
    draw.text((ox,53),'Folded onto top panel (UV, mm)',font=small,fill='#455168')
    panel=next(p for p in net['panels'] if p['key']=='z+')
    draw.polygon([pt(p) for p in panel['outer_loop']['points']],fill=(225,233,243,255),outline='#304860',width=2)
    for tab in net['overlaps']:
        if tab['target_panel']=='z+':draw.polygon([pt(p) for p in tab['receiving_uv']],fill=(230,168,40,145),outline='#8d5800',width=2)
    if i==0:
        region=shape(diagnostic['geometry']);draw.polygon([pt(p) for p in region.exterior.coords],fill=(220,45,45,195),outline='#a00000',width=2)
        draw.text((ox,410),'FAIL: 15 x 15 mm conflict located',font=small,fill='#b42318')
    else:draw.text((ox,410),'PASS: alternative fully rechecked',font=small,fill='#137447')
    draw.text((ox,438),'Tab width stays 15 mm; volume unchanged',font=small,fill='#455168')
    (out/f'candidate-{i}.json').write_text(json.dumps(net,indent=2)+'\n')
canvas.save(out/'corner-options.png')
files=[dict(path=str(p.relative_to(ROOT)),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size) for p in sorted(out.iterdir()) if p.is_file()]
result=dict(status='pass',failed_case_count=1,passed_alternatives=2,diagnostic=diagnostic,artifacts=files)
(out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(dict(status='pass',failed_case_count=1,passed_alternatives=2)))
