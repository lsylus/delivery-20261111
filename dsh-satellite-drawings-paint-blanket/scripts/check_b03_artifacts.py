"""Regenerate and compare real source/new facts and audit their input bytes."""
import hashlib, importlib.metadata, json, math, os, platform, subprocess, sys
from pathlib import Path
from b03_cases import SOURCE, CAD
from verify_batch import prerequisite_artifact_matches

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/B03'

def file_record(path):
    data=path.read_bytes()
    return dict(path=str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))

def compare(a,b,path='root'):
    if isinstance(a,dict):
        assert a.keys()==b.keys(),path
        for key in a:compare(a[key],b[key],path+'/'+key)
    elif isinstance(a,list):
        assert len(a)==len(b),path
        for i,(x,y) in enumerate(zip(a,b,strict=True)):compare(x,y,f'{path}/{i}')
    elif isinstance(a,(int,float)) and not isinstance(a,bool):
        assert math.isclose(a,b,rel_tol=1e-6,abs_tol=1e-6), (path,a,b)
    else: assert a==b,(path,a,b)

def check():
    prior=json.loads((OUT/'prerequisites.json').read_text())
    summary_path=ROOT/'docs/evidence/B02/summary.json'
    assert file_record(summary_path)['sha256']==prior['B02_summary_sha256']
    assert file_record(ROOT/'docs/reviews/B02.md')['sha256']==prior['B02_review_sha256']
    summary=json.loads(summary_path.read_text())
    assert summary['status']=='passed'
    assert all(prerequisite_artifact_matches(ROOT,summary['code_revision'],r) for r in summary['inputs']+summary['artifacts'])
    provenance=json.loads((OUT/'source-provenance.json').read_text())
    assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==provenance['source_revision']
    for r in provenance['sources']+provenance['inputs']:
        assert file_record(Path(r['path']))=={k:r[k] for k in ('path','sha256','bytes')}
    commands=[]
    values={}
    for mode in ('source','new'):
        path=OUT/'characterization'/f'{mode}.json'
        argv=[sys.executable,'scripts/probe_b03.py',mode,str(path)]
        result=subprocess.run(argv,cwd=ROOT,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=240)
        log=OUT/f'probe-{mode}.log';log.write_text(result.stdout+result.stderr)
        commands.append(dict(argv=argv,exit_code=result.returncode,log_ref=str(log.relative_to(ROOT))))
        if result.returncode: raise RuntimeError(f'{mode} probe failed: {result.stderr}')
        values[mode]=json.loads(path.read_text())
    compare(values['source'],values['new'])
    compare(json.loads((OUT/'characterization/source-before.json').read_text()),values['source'])
    result=dict(status='pass',commands=commands,pair_count=len(values['new']['pairs']),patch_count=len(values['new']['patches']),
        input_hashes=values['new']['inputs'],outputs=[file_record(OUT/'characterization'/f'{mode}.json') for mode in ('source','new')],
        source_files_revalidated=len(provenance['sources']),prerequisite_entries_revalidated=len(summary['inputs'])+len(summary['artifacts']),
        numeric_oracle='length abs 1e-6 mm, area/volume rel 1e-6, explicit near-zero abs 1e-9 in pytest; not manufacturing tolerances',
        resources_created=[],resources_cleaned=[])
    (OUT/'measurements.json').write_text(json.dumps(result,indent=2)+'\n')
    environment=dict(status='pass',python=sys.version,platform=platform.platform(),machine=platform.machine(),packages={name:importlib.metadata.version(name) for name in ['cadquery','cadquery-ocp','numpy','pytest']})
    (OUT/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    print(json.dumps(dict(status='pass',pairs=result['pair_count'],patch_cases=result['patch_count'])))

if __name__=='__main__':
    try:check()
    except Exception as exc:
        (OUT/'measurements.json').write_text(json.dumps(dict(status='fail',reason=str(exc)),indent=2)+'\n')
        raise
