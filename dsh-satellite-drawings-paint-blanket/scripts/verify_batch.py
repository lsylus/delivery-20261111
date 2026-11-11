"""Fail-closed batch verification. Only registered real test suites may pass."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def safe(root,relative):
    p=(root/relative).resolve()
    if not p.is_relative_to(root.resolve()):raise ValueError('path outside project')
    return p

def test_counts(xml_path,expected_paths):
    tree=ET.parse(xml_path)
    cases=tree.findall('.//testcase')
    failed=sum(c.find('failure') is not None or c.find('error') is not None for c in cases)
    skipped=sum(c.find('skipped') is not None for c in cases)
    # Every registered test file must actually contribute tests, not just be present.
    observed={c.get('classname','').rsplit('.',1)[0] if c.get('classname','').endswith('Tests') else c.get('classname','') for c in cases}
    missing=[p for p in expected_paths if not any(o==p.removesuffix('.py').replace('/','.') or o.startswith(p.removesuffix('.py').replace('/','.')+'.') for o in observed)]
    return {'required':len(cases),'passed':len(cases)-failed-skipped,'failed':failed,'skipped_required':skipped},missing

def assess(counts,commands,checks,missing_test_files=(),blocked_exit_codes=()):
    if counts['failed'] or any(c['exit_code'] not in (0,5,*blocked_exit_codes) for c in commands):return 'failed'
    if counts['required']==0 or counts['skipped_required'] or missing_test_files:return 'blocked'
    if counts['passed']!=counts['required']:return 'blocked'
    if any(c['exit_code']!=0 for c in commands):return 'blocked'
    if any(c['status']!='pass' for c in checks):return 'blocked'
    return 'passed'

def prerequisite_artifact_matches(root, revision, artifact):
    # Prerequisite source hashes bind its tested commit, not a later batch's edits.
    # Runtime evidence binds the final archived bytes, not a pre-acceptance copy.
    path = safe(root, artifact['path'])
    if artifact['path'].startswith('docs/evidence/'):
        return path.is_file() and sha(path) == artifact['sha256']
    blob = subprocess.run(['git','show',f"{revision}:{artifact['path']}"],cwd=root,capture_output=True)
    if blob.returncode == 0:
        return hashlib.sha256(blob.stdout).hexdigest() == artifact['sha256']
    return path.is_file() and sha(path) == artifact['sha256']

def verify(batch,report_dir,root=ROOT,registry_path=None):
    root=root.resolve(); report_dir=Path(report_dir).resolve()
    if not report_dir.is_relative_to(root):raise ValueError('report directory must be inside NEW_ROOT')
    report_dir.mkdir(parents=True,exist_ok=True)
    registry=json.loads((registry_path or root/'scripts/batches.json').read_text())
    entry=registry.get(batch)
    try:revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
    except subprocess.CalledProcessError:revision=None
    dirty=bool(subprocess.check_output(['git','status','--porcelain','--untracked-files=all'],cwd=root,text=True))
    result={'schema_version':1,'batch_id':batch,'status':'blocked','code_revision':revision,'dirty':dirty,'prerequisites':[],'commands':[],'tests':{'required':0,'passed':0,'failed':0,'skipped_required':0},'inputs':[],'artifacts':[],'checks':[],'manual_evidence':[],'limitations':[],'resources_created':[],'resources_cleaned':[]}
    def check(id_,ok,reason):result['checks'].append({'id':id_,'status':'pass' if ok else 'blocked','reason':reason})
    def save():
        from contracts import validate
        validate('summary',result)
        (report_dir/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        return 0 if result['status']=='passed' else 2
    if entry is None:
        result['limitations'].append('Unknown/unimplemented batch; no default passing entry.');return save()
    paths=entry.get('tests',[])
    if not paths or any(not safe(root,p).is_file() for p in paths):
        result['limitations'].append('No registered tests or required test file missing.');return save()
    for prereq in entry.get('prerequisites',[]):
        p=safe(root,prereq['summary'])
        try:
            from contracts import validate
            if 'development_policy' in prereq:
                from check_b10_prerequisites import check_development
                check_development(root,batch,prereq)
                ok=True
            else:
                data=json.loads(p.read_text());validate('summary',data)
                ok=data['status']=='passed' and data['tests']['required']>0 and data['tests']['skipped_required']==0
                ok=ok and bool(data.get('code_revision')) and subprocess.run(['git','merge-base','--is-ancestor',data['code_revision'],'HEAD'],cwd=root,capture_output=True).returncode==0
                ok=ok and bool(data.get('artifacts')) and all(prerequisite_artifact_matches(root,data['code_revision'],a) for a in data['artifacts'])
        except Exception:ok=False
        result['prerequisites'].append({'summary':prereq['summary'],'status':'pass' if ok else 'blocked'})
        check('prerequisite:'+prereq['summary'],ok,prereq.get('development_policy','passed real evidence, ancestor commit and artifact hashes required'))
    if batch in ('B10','B11'):check('clean_start',not dirty,batch+' acceptance must start from committed clean source')
    if any(c['status']!='pass' for c in result['checks']):return save()
    env=os.environ.copy();env['PATH']=str(root/'.tools/node/bin')+os.pathsep+env.get('PATH','')
    if batch=='B11':
        temporary=root/'work/b11-test-temporary';temporary.mkdir(parents=True,exist_ok=True)
        env['TMPDIR']=str(temporary)
    junit=report_dir/'pytest.xml'
    # No stale XML/evidence may survive a failed command and be interpreted as current.
    if junit.exists():junit.unlink()
    for rel in entry.get('generated_evidence',[]):
        p=safe(root,rel)
        if p.exists():p.unlink()
    commands=[[sys.executable if x=='{python}' else x for x in cmd] for cmd in entry.get('pre_commands',[])]
    commands += [[sys.executable,'-m','pytest','-q',*paths,f'--rootdir={root}',f'--junitxml={junit}']]
    commands += [[sys.executable if x=='{python}' else x for x in cmd] for cmd in entry.get('commands',[])]
    for index,cmd in enumerate(commands):
        log=report_dir/f'command-{index+1:02}.log'
        try:
            with log.open('w') as f:
                p=subprocess.run(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=entry.get('timeout_s',1200));code=p.returncode
        except (OSError,subprocess.TimeoutExpired) as e:
            log.write_text(str(e)+'\n');code=124
        result['commands'].append({'argv':cmd,'exit_code':code,'log_ref':str(log.relative_to(root))})
    missing=[]
    try:result['tests'],missing=test_counts(junit,paths)
    except (OSError,ET.ParseError) as e:check('junit',False,str(e))
    check('test_files_executed',not missing,str(missing) if missing else 'Every registered test file contributed real test cases')
    for rule in entry.get('evidence',[]):
        p=safe(root,rule['path']);ok=p.is_file() and p.stat().st_size>0
        reason='file, content checks and hash'
        if ok and rule.get('json_status'):
            try:ok=json.loads(p.read_text()).get('status')==rule['json_status']
            except (ValueError,OSError):ok=False
        if ok and rule.get('schema'):
            try:
                from contracts import validate
                validate(rule['schema'],json.loads(p.read_text()),rule.get('definition'))
            except Exception as e:ok=False;reason=str(e)
        check(rule['path'],ok,reason)
        if p.is_file():result['artifacts'].append({'path':rule['path'],'sha256':sha(p),'bytes':p.stat().st_size})
    for rule in entry.get('manual_evidence',[]):
        p=safe(root,rule['path'])
        try:
            data=json.loads(p.read_text());ok=all(data.get(k) for k in ('reviewer','scope','revision_id','evidence_refs')) and data.get('decision')=='approved'
            ok=ok and all(safe(root,e['path']).is_file() and sha(safe(root,e['path']))==e['sha256'] for e in data['evidence_refs'])
        except (OSError,ValueError,KeyError,TypeError):ok=False
        check('manual:'+rule['path'],ok,'Named reviewer, reviewed revision and hashed evidence required')
        if ok:result['manual_evidence'].append(data)
    for path in entry.get('inputs',[]):
        p=safe(root,path);check('input:'+path,p.is_file(),'registered input manifest required')
        if p.is_file():result['inputs'].append({'path':path,'sha256':sha(p),'bytes':p.stat().st_size})
    result['limitations']=entry.get('limitations',[])
    for rel in entry.get('resource_records',[]):
        try:
            data=json.loads(safe(root,rel).read_text())
            result['resources_created']+=data.get('resources_created',[]);result['resources_cleaned']+=data.get('resources_cleaned',[])
        except (ValueError,OSError):pass
    result['status']=assess(result['tests'],result['commands'],result['checks'],missing,entry.get('blocked_exit_codes',[]))
    # Include exact tested code hashes so dirty implementations remain reviewable.
    for path in sorted(set(paths+['scripts/verify_batch.py','scripts/batches.json'])):
        p=safe(root,path)
        if p.is_file() and not any(a['path']==path for a in result['artifacts']):result['artifacts'].append({'path':path,'sha256':sha(p),'bytes':p.stat().st_size})
    return save()

def main():
    p=argparse.ArgumentParser();p.add_argument('batch');p.add_argument('--report-dir',required=True);args=p.parse_args()
    try:return verify(args.batch,args.report_dir)
    except Exception as e:
        print(f'BLOCKED: {e}',file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
