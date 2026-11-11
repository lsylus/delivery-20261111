"""Clean-source R3 execution evidence. Success remains blocked pending review."""
import os,sys,json,subprocess,argparse
from pathlib import Path
from verify_development import code_fingerprint,digest
from verify_batch import test_counts
ROOT=Path(__file__).resolve().parents[1]
GROUPS={
 'blanket':['tests/blanket/'+name+'.py' for name in (
 'test_positive_clearance_cover','test_complex_envelope','test_developable','test_piecewise_mapping',
 'test_native_surface_manufacturing','test_sphere_atlas','test_sphere_material_connectivity',
 'test_unfold','test_overlaps','test_foldback','test_fixed_points','test_seam_pairing',
 'test_net_contracts','test_contracts','test_baseline_revision','test_cover_openings','test_net_runtime')],
 'paint':['tests/paint/'+name+'.py' for name in (
 'test_real_radial_boss','test_curved_native_footprints','test_native_surface_result','test_complex_targets',
 'test_contact_footprints','test_feature_protection','test_region_clipping','test_review_regressions','test_paint_failure','test_paint_runtime')],
 'integration':['tests/integration/test_revision_rebinding.py','tests/integration/test_b13_workflow.py',
 'tests/contracts/test_schemas.py','tests/contracts/test_b13_gate.py','tests/geometry/test_complete_b13_import.py']}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report-dir',required=True);args=parser.parse_args()
    out=(ROOT/args.report_dir).resolve();assert out.is_relative_to(ROOT) and not out.exists()
    # Capture clean start BEFORE any tracked evidence directory is created.
    rev=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert not subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'],cwd=ROOT),'Clean committed source required'
    fp=code_fingerprint();out.mkdir(parents=True)
    env=dict(os.environ,B13_EVIDENCE_DIR=str(out.relative_to(ROOT)),PATH=str(ROOT/'.tools/node/bin')+os.pathsep+os.environ['PATH'])
    commands=[['npm','run','build'],['npm','run','typecheck']]
    for name,files in GROUPS.items():commands.append([sys.executable,'-m','pytest','-q',*files,'--junitxml='+str(out/(name+'.xml'))])
    commands += [['npm','run','test','--workspace','packages/host-bridge'],
        [sys.executable,'scripts/check_b13_prerequisites.py'],
        [sys.executable,'scripts/b13_r3_blanket_workflow.py'],[sys.executable,'scripts/b13_r3_paint_workflow.py'],
        [sys.executable,'scripts/audit_b13_r3_serialized.py'],[sys.executable,'scripts/run_b13_r3_browser.py'],
        [sys.executable,'scripts/check_source_boundary.py','--output',str(out/'source-boundary.json')]]
    records=[]
    for i,cmd in enumerate(commands,1):
        log=out/f'command-{i:02}.log';print('RUN',i,cmd,flush=True);timed_out=False
        with log.open('w') as f:
            process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=f,stderr=subprocess.STDOUT)
            try:code=process.wait(timeout=2400)
            except subprocess.TimeoutExpired:
                timed_out=True;process.terminate();code=process.wait(timeout=60)
        records.append(dict(argv=cmd,native_exit_code=code,timed_out=timed_out,log_ref=str(log.relative_to(ROOT)),log_sha256=digest(log)))
        print('EXIT',i,code,flush=True)
        if code or timed_out:break
    counts={};missing=[]
    for name,files in GROUPS.items():
        if (out/(name+'.xml')).exists():counts[name],absent=test_counts(out/(name+'.xml'),files);missing+=absent
        else:missing+=files
    checks=[]
    for name in ['prerequisites.json','blanket-http/workflow.json','paint-http/workflow.json','serialized-audit.json','browser-acceptance.json','browser-resources.json','source-boundary.json']:
        try:ok=json.loads((out/name).read_text())['status']=='pass'
        except (OSError,ValueError,KeyError):ok=False
        checks.append(dict(path=name,status='pass' if ok else 'fail'))
    unchanged=fp==code_fingerprint()
    ok=len(records)==len(commands) and unchanged and not missing and all(c['native_exit_code']==0 and not c['timed_out'] for c in records) and all(c['status']=='pass' for c in checks) and all(c['required']==c['passed']>0 and c['failed']==c['skipped_required']==0 for c in counts.values())
    value=dict(schema_version=1,batch_id='B13',round='R3',status='blocked' if ok else 'failed',scope_tests_status='passed' if ok else 'failed',full_acceptance=False,code_revision=rev,code_fingerprint=fp,dirty=False,source_unchanged=unchanged,commands=records,tests=counts,missing_test_files=missing,checks=checks,
        independent_review=dict(status='pending',prior_report='docs/reviews/B13-r2.md',prior_exact_scope='PASS',prior_whole_batch_technical_completion='FAIL'),
        blockers=['User confirms no sphere manufacturing standard; 272/1073/4126 sampled candidates remain blocked',
        'Motor installation frame, openings, clearance and interface process classification remain engineering candidates',
        'Trim representation measurements are not global curve approximation certification',
        'B04 AutoCAD, B05 authorized native conversion, B07 formal DSH, B09/B12 full blockers retained'])
    (out/'development.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps({k:value[k] for k in ['status','scope_tests_status','tests','code_revision','source_unchanged']}),flush=True)
    return 2 if ok else 1
if __name__=='__main__':raise SystemExit(main())
