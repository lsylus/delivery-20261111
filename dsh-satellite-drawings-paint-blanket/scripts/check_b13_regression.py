"""Run each established collection environment separately, retaining native exits."""
import json,subprocess,sys,os

from pathlib import Path
from verify_batch import test_counts
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/os.environ.get('B13_EVIDENCE_DIR','docs/evidence/B13')/'regression';out.mkdir(parents=True,exist_ok=True)
groups=[['tests/runtime','tests/contracts'],['tests/integration/test_b09_commands.py','tests/integration/test_paint_workflow.py'],['tests/paint'],['tests/geometry'],['tests/blanket/'+n+'.py' for n in ['test_box_allowance','test_envelope_volume','test_baseline_revision','test_cover_openings','test_contracts','test_runtime','test_gate']],['tests/formats/test_drawing_document.py','tests/formats/test_dxf_roundtrip.py'],['tests/blanket/test_unfold.py','tests/blanket/test_seam_pairing.py','tests/blanket/test_overlaps.py','tests/blanket/test_fixed_points.py','tests/blanket/test_foldback.py','tests/blanket/test_net_runtime.py','tests/blanket/test_net_contracts.py']]
temporary=ROOT/'work/b13-regression-temporary';temporary.mkdir(parents=True,exist_ok=True)
os.environ['TMPDIR']=str(temporary)
records=[]
for i,group in enumerate(groups,1):
    xml=out/f'group-{i}.xml';xml.unlink(missing_ok=True);log=out/f'group-{i}.log'
    argv=[sys.executable,'-m','pytest','-q',*group,f'--rootdir={ROOT}',f'--junitxml={xml}']
    with log.open('w') as f:r=subprocess.run(argv,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,timeout=1200)
    counts,_=test_counts(xml,[]) if xml.exists() else (dict(required=0,passed=0,failed=0,skipped_required=0),[])
    records.append(dict(argv=argv,exit_code=r.returncode,tests=counts,log_ref=str(log.relative_to(ROOT))))
    print(i,r.returncode,counts,flush=True)
ok=all(r['exit_code']==0 and r['tests']['required']==r['tests']['passed']>0 and r['tests']['skipped_required']==0 for r in records)
(out/'summary.json').write_text(json.dumps(dict(status='pass' if ok else 'fail',commands=records),indent=2)+'\n')
raise SystemExit(0 if ok else 1)
