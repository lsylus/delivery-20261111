"""Read-only guard for G/T/S/H; hashes untracked files and tracked modifications."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def git(root,*args): return subprocess.check_output(['git','-C',str(root),*args])
def file_hash(p):
    h=hashlib.sha256()
    if p.is_symlink(): h.update(os.readlink(p).encode())
    else:
        with p.open('rb') as f:
            for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def snapshot(root):
    status=git(root,'status','--porcelain=v1','--untracked-files=all')
    untracked={os.fsdecode(p):file_hash(root/os.fsdecode(p)) for p in git(root,'ls-files','--others','--exclude-standard','-z').split(b'\0') if p}
    return {'head':git(root,'rev-parse','HEAD').decode().strip(),'branch':git(root,'branch','--show-current').decode().strip(),'status_sha256':hashlib.sha256(status).hexdigest(),'diff_sha256':hashlib.sha256(git(root,'diff','--binary','HEAD')).hexdigest(),'untracked':untracked}

def check(root=ROOT):
    provenance=json.loads((root/'docs/evidence/B01/source-provenance.json').read_text())
    records=[]
    for alias,expected in provenance['sources'].items():
        old=Path(expected['path']).resolve()
        if root.resolve().is_relative_to(old): raise ValueError('NEW_ROOT is inside reference repository')
        actual=snapshot(old)
        differences=[k for k in actual if actual[k]!=expected[k]]
        records.append({'source':alias,'path':str(old),'status':'pass' if not differences else 'fail','differences':differences,'head':actual['head'],'status_sha256':actual['status_sha256'],'diff_sha256':actual['diff_sha256'],'untracked_count':len(actual['untracked'])})
    return {'schema_version':1,'new_root':str(root.resolve()),'status':'pass' if all(r['status']=='pass' for r in records) else 'fail','sources':records,'scope':'HEAD, branch, complete porcelain status, tracked diff bytes, nonignored untracked content; ignored runtime data not inspected or written'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output');args=parser.parse_args()
    try: result=check()
    except Exception as e:result={'status':'blocked','reason':str(e)}
    text=json.dumps(result,indent=2,ensure_ascii=False)
    print(text)
    if args.output: Path(args.output).write_text(text+'\n')
    return 0 if result['status']=='pass' else 2

if __name__=='__main__':raise SystemExit(main())
