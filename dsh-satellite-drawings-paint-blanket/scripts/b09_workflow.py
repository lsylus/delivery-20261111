"""Real HTTP/worker exercise shared by scoped acceptance and integration tests."""
import sys,json,hashlib,copy,os,signal
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/paint'))
from http_case import Service,imported_case,download

def configured_service(base):
 s=Service(base,timeout=180,upload_limit=64*1024*1024)
 s.stop();config=json.loads(s.config.read_text());config['converter_config']=str(ROOT/'work/config/converters.local.json');s.config.write_text(json.dumps(config));s.start()
 return s

def head(s,p):
 id_=s.call('GET',f'/projects/{p}')[1]['module_states']['paint']
 return s.call('GET',f'/projects/{p}/revisions/{id_}')[1]

def result(s,p):return s.call('GET',f'/projects/{p}/paint-result')[1]

def completed(s,p,rev,op,params=None):
 r=s.wait(s.operation(p,rev,op,params)['run_id'])
 assert r['state']=='succeeded',(r,[x.read_text() for x in (s.data/'jobs').glob('*.log')])
 return r

def generate_case(s):
 p,rev,_,_=imported_case(s)
 r=completed(s,p,rev,'paint.generate',rev['parameters'])
 assert result(s,p)['paint']['status']=='passed'
 return p,rev,r

def signature(paint):
 return dict(regions=[{k:v for k,v in r.items() if k not in ('id','check_refs')} for r in paint['regions']],overlay=[{k:v for k,v in r.items() if k!='region_id'} for r in paint['overlay']],
             entities=[{k:v for k,v in e.items() if k!='id'} for e in paint['drawing_document']['entities']])

def exercise(s,out):
 out.mkdir(parents=True,exist_ok=True)
 p,rev,generated=generate_case(s);initial=result(s,p)
 # This square is clear material on the 100x80 plate, away from its source hole.
 polygon=[[-45,25],[-35,25],[-35,35],[-45,35]]
 command=dict(result_id=initial['result_id'],action='add',points=polygon,reason='B09 explicit technical reference square 100 mm2')
 edited=completed(s,p,rev,'paint.edit_regions',command);edit_rev=head(s,p);after=result(s,p)
 assert edit_rev['id']!=rev['id'] and after['paint']['revision_id']==edit_rev['id']
 assert abs(sum(r['area_mm2'] for r in after['paint']['regions'])-sum(r['area_mm2'] for r in initial['paint']['regions'])-100)<1e-6
 assert len(edit_rev['document_edits'])==1
 s.operation(p,rev,'paint.edit_regions',command,expected=409)
 s.operation(p,edit_rev,'drawing.export',dict(result_id=initial['result_id'],draft=True),expected=409)
 completed(s,p,edit_rev,'history.undo');assert head(s,p)['id']==rev['id'] and signature(result(s,p)['paint'])==signature(initial['paint'])
 completed(s,p,rev,'history.redo');assert head(s,p)['id']==edit_rev['id'] and signature(result(s,p)['paint'])==signature(after['paint'])
 note=completed(s,p,edit_rev,'drawing.edit_annotation',dict(result_id=after['result_id'],annotation_id='note',text='保护区域待复核',position=[-45,-37]))
 note_rev=head(s,p);noted=result(s,p)
 assert noted['paint']['overlay']==[{**o,'region_id':o['region_id'].replace(edit_rev['id'],note_rev['id'])} for o in after['paint']['overlay']]
 saved=completed(s,p,note_rev,'engineering.save');bundle=next(a for a in saved['artifacts'] if a['role']=='engineering_bundle')
 s.stop();s.start()
 restored=completed(s,p,note_rev,'engineering.restore',{'artifact_id':bundle['id']});restored_rev=head(s,p)
 assert signature(result(s,p)['paint'])==signature(noted['paint']) and restored_rev['document_edits']==note_rev['document_edits']
 paint=result(s,p)
 exported=completed(s,p,restored_rev,'drawing.export',dict(result_id=paint['result_id'],draft=True));files=download(s,exported)
 assert files['drawing.dwg'][:6]==b'AC1032'
 evidence=json.loads(files['conversion.json']);assert evidence['status']=='needs_review' and evidence['draft'] and not evidence['full_acceptance']
 assert all(c['exit_code']==0 for c in evidence['commands']) and evidence['capability']['real_conversion_verified']
 assert all(a['validation'][0]['status']=='needs_review' for a in exported['artifacts'])
 for a in exported['artifacts']:s.call('GET',a['download_url'].removeprefix('/api/v1'),who='bob',expected=404)
 for name,data in files.items():(out/name).write_bytes(data)
 (out/'paint-result.json').write_text(json.dumps(paint['paint'],ensure_ascii=False,indent=2)+'\n')
 (out/'drawing.json').write_text(json.dumps(paint['paint']['drawing_document'],ensure_ascii=False,indent=2)+'\n')
 return dict(status='pass',scope='STEP technical workflow, analytic square reference; no manufacturing approval',project=p,initial_revision=rev['id'],edited_revision=edit_rev['id'],restored_revision=restored_rev['id'],runs=[generated,edited,note,saved,restored,exported],reference_square_mm2=100,source_sha256=hashlib.sha256((ROOT/'fixtures/synthetic/paint/assembly.step').read_bytes()).hexdigest(),artifacts=[dict(path=str(f.relative_to(ROOT)),sha256=hashlib.sha256(f.read_bytes()).hexdigest(),bytes=f.stat().st_size) for f in out.iterdir() if f.is_file()])
