"""Scoped consumption audit, without changing historical full-acceptance results."""
from pathlib import Path
import json, subprocess, hashlib
from verify_batch import prerequisite_artifact_matches
ROOT=Path(__file__).resolve().parents[1]
def main():
 records=[]
 for batch in ('B04','B07','B08'):
  p=ROOT/f'docs/evidence/{batch}/summary.json';s=json.loads(p.read_text())
  assert s['status']==('passed' if batch=='B08' else 'blocked')
  assert not s['dirty']
  assert s['tests']['required']==s['tests']['passed']>0 and not s['tests']['skipped_required']
  if batch=='B08':assert all(c['exit_code']==0 for c in s['commands']) and all(c['status']=='pass' for c in s['checks'])
  subprocess.run(['git','merge-base','--is-ancestor',s['code_revision'],'HEAD'],cwd=ROOT,check=True)
  mismatches=[a['path'] for a in s['artifacts'] if not prerequisite_artifact_matches(ROOT,s['code_revision'],a)]
  # B07 archived its .gitignore before the later same-batch edit. This is not a
  # consumed interface; retain the defect explicitly instead of rewriting B07.
  assert set(mismatches)<=({'.gitignore'} if batch=='B07' else set()),mismatches
  records.append(dict(batch=batch,full_status=s['status'],code_revision=s['code_revision'],summary_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),verified_artifacts=len(s['artifacts'])-len(mismatches),historical_unconsumed_mismatches=mismatches))
 assert '**PASS**' in (ROOT/'docs/reviews/B08.md').read_text()
 conv=json.loads((ROOT/'docs/evidence/B04/conversion.json').read_text())
 assert conv['capability']['real_conversion_verified'] and all(c['exit_code']==0 for c in conv['commands'])
 browser=json.loads((ROOT/'docs/evidence/B07/browser-acceptance.json').read_text())
 assert browser['status']=='pass' and browser['counts']['passed']>0 and browser['counts']['failed']==browser['counts']['skipped']==0
 interfaces={}
 for name in ('common','model','mesh-map','paint','operation','runtime'):
  p=ROOT/f'contracts/{name}.schema.json';interfaces[name]=dict(schema_id=json.loads(p.read_text())['$id'],sha256=hashlib.sha256(p.read_bytes()).hexdigest())
 out=ROOT/'docs/evidence/B09';out.mkdir(parents=True,exist_ok=True)
 consumed=[]
 for rel in ('docs/evidence/B04/conversion.json','docs/evidence/B07/browser-acceptance.json','docs/reviews/B08.md'):
  p=ROOT/rel;consumed.append(dict(path=rel,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size))
 (out/'prerequisites.json').write_text(json.dumps(dict(status='pass',scope='B09 development only',batches=records,interfaces=interfaces,consumed_evidence=consumed,retained=['B04 AutoCAD','B05 native converter','B07 formal DSH identity']),indent=2)+'\n')
 print('B04 conversion, B07 isolated workflow, B08 full acceptance: verified')
if __name__=='__main__':main()
