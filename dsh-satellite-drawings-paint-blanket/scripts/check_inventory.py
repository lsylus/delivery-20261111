"""Validate inventory integrity and source availability without rehashing huge CAD."""
import hashlib
import json
from pathlib import Path
from contracts import validate, digest_files

ROOT=Path(__file__).resolve().parents[1]

def main():
    data=json.loads((ROOT/'fixtures/manifests/cases.json').read_text());validate('cases',data)
    result={'status':'pass','cases':len(data['cases']),'inventory':[],'scope':'source existence/size and inventory digest; CAD bytes hashed once during registration, no geometry loading'}
    seen=set()
    for case in data['cases']:
        path=ROOT/case['source_manifest']
        if path in seen:continue
        seen.add(path);manifest=json.loads(path.read_text());files=manifest['files']
        row={'path':case['source_manifest'],'file_count':len(files),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'status':'pass'}
        if manifest['kind']=='zip_inventory_not_loaded_CAD':
            # Cross-host reference is explicit; local registration captured hash + unchanged stat.
            row['source_check']='Windows original registration; not claimed accessible at a Linux path'
            row['cad_files']=[{k:f[k] for k in ('relative_path','bytes','sha256','detected_format')} for f in files if f.get('detected_format') in ('STEP','DWG')]
            if len(row['cad_files'])!=2:row['status']='fail'
        else:
            directory=Path(manifest['source_root'])
            for record in files:
                p=(directory/record['relative_path']).resolve()
                if not p.is_relative_to(directory.resolve()) or not p.is_file() or p.stat().st_size!=record['bytes']:row['status']='fail'
            if 'inventory_digest' in manifest:
                if digest_files([{k:f[k] for k in ('relative_path','sha256','bytes')} for f in files])!=manifest['inventory_digest']:row['status']='fail'
            row['formats']={fmt:sum(f['detected_format']==fmt for f in files) for fmt in {f['detected_format'] for f in files}}
        if row['status']!='pass':result['status']='fail'
        result['inventory'].append(row)
    (ROOT/'docs/evidence/B01/inventory-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']=='pass' else 2

if __name__=='__main__':raise SystemExit(main())
