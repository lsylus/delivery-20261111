"""Operator-only new drawings backend setup/enrollment. Never reads platform secrets."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from thermal_drawings.api.host_auth import decode
from cryptography.hazmat.primitives.serialization import load_der_public_key
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

def atomic(path,value):
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.host-')
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--allowed-parent',type=Path,default=Path('/data/qmh'))
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    e=sub.add_parser('enroll');e.add_argument('--public-info',type=Path,required=True);e.add_argument('--user',required=True);e.add_argument('--tenant',default='xingqiao-9999')
    e=sub.add_parser('revoke');e.add_argument('--kid',required=True)
    e=sub.add_parser('project-access');e.add_argument('--project',required=True);e.add_argument('--owner',required=True);e.add_argument('--access',choices=['deny','read','write'],required=True)
    args=p.parse_args();root=args.root;allowed_parent=args.allowed_parent.resolve()
    if root.resolve()!=root:raise ValueError('Backend root must use a canonical path without symlink ancestors')
    if not root.is_absolute() or not root.is_relative_to(allowed_parent) or root.is_symlink():raise ValueError(f'New backend root must be under {allowed_parent}')
    if args.command=='init':
        root.mkdir(mode=0o700,parents=True,exist_ok=False)
        (root/'data').mkdir(mode=0o700)
        atomic(root/'hosts.json',{'version':1,'keys':{}})
        atomic(root/'config.json',{'auth_mode':'dsh-account','data_root':str(root/'data'),'host_registry':str(root/'hosts.json'),'bind_host':'127.0.0.1','upload_limit':67108864,'timeout_s':120,'memory_limit_mb':4096,'concurrency':1})
        print(json.dumps({'root':str(root),'configured':True,'authorized_keys':0,'status':'awaiting_platform_public_key_enrollment'}));return
    if root.stat().st_mode&0o077:raise ValueError('Private backend root required')
    registry=json.loads((root/'hosts.json').read_text())
    if args.command=='enroll':
        info=json.loads(args.public_info.read_text())
        if info['user']!=args.user or info['tenant']!=args.tenant or info['module'] not in ('paint','blanket'):raise ValueError('Explicit account/module mismatch')
        key=decode(info['public_key'])
        if not isinstance(load_der_public_key(key),Ed25519PublicKey) or hashlib.sha256(key).hexdigest()!=info['kid']:raise ValueError('Invalid public key')
        if info['home_hash']!=hashlib.sha256(args.user.encode()).hexdigest():raise ValueError('Account home mismatch')
        registry['keys'][info['kid']]={k:info[k] for k in ['tenant','user','home_hash','module','public_key']}
        registry['keys'][info['kid']]['enabled']=True
        atomic(root/'hosts.json',registry)
        print(json.dumps({'enrolled_kid':info['kid'],'user':args.user,'module':info['module']}))
    elif args.command=='revoke':
        registry['keys'][args.kid]['enabled']=False;atomic(root/'hosts.json',registry);print('Host key revoked; next request denied')
    else:
        db=sqlite3.connect(root/'data/engineering.sqlite3')
        try:
            if not db.execute('SELECT id FROM projects WHERE id=? AND owner=?',(args.project,args.owner)).fetchone():raise ValueError('Project owner mismatch')
            db.execute('INSERT OR REPLACE INTO host_project_access VALUES(?,?,?,?)',(args.project,args.owner,int(args.access!='deny'),int(args.access=='write')));db.commit()
        finally:db.close()
        print('Project access updated')

if __name__=='__main__':main()
