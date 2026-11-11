"""Give only the observed DSH account read/execute access to this delivery.

Preserve other principals' effective rights when widening an ACL mask. Keep
the original complete ACLs as rollback evidence; do not change package bytes.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess

ROOT = Path('/data/qmh/satellite-plugins-20261029/dsh-satellite-heater-drawing')
ACCOUNT = 'xie'
UID = pwd.getpwnam(ACCOUNT).pw_uid
assert UID == 1001
archive = ROOT/'dist/plugin-release-20261110/qmh-dsh-satellite-heater-drawing-0.2.0.tgz'
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
trees = [(ROOT/'.python/cpython-3.12-linux-x86_64-gnu').resolve(),
         Path('/data/qmh/OpenCADStudio/current/squashfs-root').resolve()]
singles = {ROOT/'dist': '--x', ROOT/'dist/plugin-release-20261110': 'r-x',
           archive: 'r--', ROOT/'dist/plugin-release-20261110/SHA256SUMS.txt': 'r--',
           ROOT/'dist/plugin-release-20261110/acceptance-summary.json': 'r--',
           ROOT/'dist/plugin-release-20261110/验收报告.md': 'r--',
           ROOT/'.python': '--x', ROOT/'fixtures/case/HZDX.SHX': 'r--'}
evidence = ROOT/'docs/evidence/installation-access-20261110'
evidence.mkdir(parents=True,exist_ok=True)
original = subprocess.check_output(['getfacl','-R','-P','-p','-n',*map(str,trees)],text=True)
original += subprocess.check_output(['getfacl','-p','-n',*map(str,singles)],text=True)
backup = evidence/'acl-before.txt'
assert not backup.exists(), 'Do not overwrite the original rollback ACLs'
backup.write_text(original)
os.chmod(backup,0o600)

def intersect(a,b):
    return ''.join(x if x == y else '-' for x,y in zip(a,b))

def union(a,b):
    return ''.join(x if x != '-' else y for x,y in zip(a,b))

modified=[]
changed=[]
for block in original.strip().split('\n\n'):
    lines=block.splitlines()
    filename=next(line[8:] for line in lines if line.startswith('# file: '))
    filename=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),filename)
    path=Path(filename)
    assert path in singles or any(path.is_relative_to(tree) for tree in trees)
    info=path.stat()
    desired=singles.get(path,'r-x' if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 'r--')
    mask=next((line.split(':')[2] for line in lines if line.startswith('mask::')),'rwx')
    entries={}
    for line in lines:
        if line.startswith(('user:','group:','mask:','other:')):
            kind,name,permissions=line.split(':')[:3]
            permissions=permissions.split()[0]
            entries[kind+':'+name]=permissions
    old=entries.get('user:'+str(UID))
    effective=intersect(old,mask) if old is not None else None
    # Skip a principal whose existing named ACL already suffices.
    if effective is not None and intersect(effective,desired)==desired:
        continue
    new_mask=union(mask,desired)
    output=[]
    inserted=False
    for line in lines:
        if line.startswith('user:'+str(UID)+':'):
            continue
        if line.startswith(('group:','mask:')) or (line.startswith('user:') and not line.startswith('user::')):
            line=line.split('\t')[0].split(' #')[0]
            kind,name,permissions=line.split(':')
            if kind=='mask':
                line='mask::'+new_mask
            else:
                # Existing mask-limited entries keep their effective rights.
                line=kind+':'+name+':'+intersect(permissions,mask)
        if line.startswith('group::'):
            output.append('user:'+str(UID)+':'+union(effective or '---',desired))
            inserted=True
        if line.startswith(('# owner:','# group:')):
            continue
        output.append(line)
    assert inserted
    if not any(line.startswith('mask::') for line in output):
        output.insert(-1,'mask::'+new_mask)
    modified.append('\n'.join(output))
    changed.append(str(path))

patch='\n\n'.join(modified)+'\n\n'
(evidence/'acl-applied.txt').write_text(patch)
subprocess.run(['setfacl','--restore=-'],input=patch,text=True,check=True)
after=subprocess.check_output(['getfacl','-R','-P','-p','-n',*map(str,trees)],text=True)
after+=subprocess.check_output(['getfacl','-p','-n',*map(str,singles)],text=True)
(evidence/'acl-after.txt').write_text(after)
for block in after.strip().split('\n\n'):
    lines=block.splitlines()
    filename=next(line[8:] for line in lines if line.startswith('# file: '))
    filename=re.sub(r'\\([0-7]{3})',lambda m:chr(int(m[1],8)),filename)
    path=Path(filename)
    info=path.stat()
    desired=singles.get(path,'r-x' if stat.S_ISDIR(info.st_mode) or info.st_mode & 0o111 else 'r--')
    granted=next(line.split(':')[2].split()[0] for line in lines if line.startswith('user:'+str(UID)+':'))
    mask=next(line.split(':')[2] for line in lines if line.startswith('mask::'))
    assert intersect(intersect(granted,mask),desired)==desired,(filename,desired)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==digest
summary={'status':'passed','account':ACCOUNT,'uid':UID,'port':9999,
         'reason':'DSH process account could not traverse dist or read package and external runtime resources',
         'archive':str(archive),'sha256_unchanged':digest,'modified_paths':len(changed),
         'permission_scope':'named account read/execute only; existing other principals effective ACL rights preserved',
         'actual_installation':'not_performed','verification':'effective named ACLs checked on every runtime path'}
(evidence/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False))
