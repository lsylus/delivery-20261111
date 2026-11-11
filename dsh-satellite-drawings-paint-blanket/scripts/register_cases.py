"""Read source headers and stream hashes, never load CAD or change sources."""
import argparse
import hashlib
import json
from pathlib import Path
from contracts import validate, digest_files

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path('/data/qmh/satellite-plugins-20261029/dsh-satellite-geometry')

def hash_file(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def inventory(directory):
    records=[]
    for p in sorted(directory.rglob('*')):
        if not p.is_file():continue
        before=p.stat()
        with p.open('rb') as f:head=f.read(4096)
        format_='Creo_ASSEMBLY' if b'#UGC:2 ASSEMBLY' in head else 'Creo_PART' if b'#UGC:2 PART' in head else 'STEP' if b'ISO-10303-21' in head else 'unknown'
        sha=hash_file(p);after=p.stat()
        if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise RuntimeError(f'source changed during read: {p}')
        records.append({'relative_path':p.relative_to(directory).as_posix(),'bytes':before.st_size,'sha256':sha,'detected_format':format_,'header_sample':head[:160].decode('ascii',errors='replace')})
    if not records:raise RuntimeError(f'empty or inaccessible source directory: {directory}')
    return {'schema_version':1,'kind':'inventory_not_loaded_assembly','source_root':str(directory),'files':records,'inventory_digest':digest_files([{k:f[k] for k in ('relative_path','sha256','bytes')} for f in records]),'completeness':'not_opened','main_assembly':None,'reason':'headers and names do not prove complete assembly or main entry'}

def case(id_,module,purpose,split,manifest,main,vendor,version,refs,tools):
    values={'id':id_,'module':module,'purpose':purpose,'split':split,'source_manifest':manifest,'main_file':main,'vendor':vendor,'version':version,'expected_instances':None,'reference_artifacts':refs,'revision_match_status':'unknown','selection_spec':None,'expected_checks':['units','assembly_completeness','revision_correspondence'],'tolerances':None,'requires_tools':tools,'completeness':'not_opened'}
    values['unknown_reasons']={k:'Not established by B01 inventory; requires actual opening and case review in its owning batch.' for k,v in values.items() if v is None}
    return values

def main():
    p=argparse.ArgumentParser();p.add_argument('--refresh',action='store_true',help='explicitly rehash controlled source files');args=p.parse_args()
    dest=ROOT/'fixtures/manifests';dest.mkdir(parents=True,exist_ok=True)
    cases=[]
    for n in range(1,5):
        name=f'Star{n}';out=dest/f'{name}.inventory.json'
        if args.refresh or not out.exists():
            out.write_text(json.dumps(inventory(SOURCE/'runtime/tianyuan-geometry-20261008/inputs'/name),ensure_ascii=False,indent=2)+'\n')
        data=json.loads(out.read_text())
        refs=[f['relative_path'] for f in data['files'] if f['detected_format']=='STEP'] or None
        cases.append(case(name,'shared','Native assembly candidate; select a complete small subassembly in B05','holdout' if n in (3,4) else 'development',f'fixtures/manifests/{out.name}',None,'Creo',None,refs,['licensed-native-converter']))
    zip_data=json.loads((dest/'zip.inventory.json').read_text())
    cad=[f for f in zip_data['files'] if f.get('detected_format') in ('STEP','DWG')]
    for f in cad:
        cases.append(case('zip-step' if f['detected_format']=='STEP' else 'zip-dwg','paint','Original supplied STEP/DWG; revision match unverified','holdout','fixtures/manifests/zip.inventory.json',f['relative_path'],'Creo' if f['detected_format']=='STEP' else 'AutoCAD',None,None,['STEP-reader'] if f['detected_format']=='STEP' else ['DWG-reader','AutoCAD-reopen']))
    for name in ['catch-original','real-thruster','real-gearbox','satellite-assembly']:
        directory=SOURCE/'cases'/name
        out=dest/f'{name}.inventory.json'
        # Only the requested original STEP, not neighboring service runtime artifacts.
        original=directory/'original.step'
        if not original.is_file():raise RuntimeError(f'missing sample: {original}')
        if args.refresh or not out.exists():
            with original.open('rb') as f:header=f.read(160).decode('ascii',errors='replace')
            out.write_text(json.dumps({'schema_version':1,'kind':'inventory_not_loaded_assembly','source_root':str(directory),'files':[{'relative_path':'original.step','bytes':original.stat().st_size,'sha256':hash_file(original),'detected_format':'STEP' if 'ISO-10303-21' in header else 'unknown','header_sample':header}],'completeness':'not_opened'},indent=2)+'\n')
        cases.append(case(name,'shared','Existing STEP candidate; no geometry or truth asserted','holdout' if name=='satellite-assembly' else 'development',f'fixtures/manifests/{out.name}','original.step',None,None,None,['STEP-reader']))
    manifest={'schema_version':1,'cases':cases};validate('cases',manifest)
    (dest/'cases.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'registered_not_opened','cases':len(cases),'holdout':[c['id'] for c in cases if c['split']=='holdout']}))

if __name__=='__main__':main()
