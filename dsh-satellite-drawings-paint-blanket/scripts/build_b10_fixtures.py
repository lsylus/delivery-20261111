from pathlib import Path
import hashlib,json
import cadquery as cq
ROOT=Path(__file__).resolve().parents[1]
out=ROOT/'fixtures/synthetic/blanket';out.mkdir(parents=True,exist_ok=True)
records=[]
for name,dims in [('box-100',(100,100,100)),('thin-long',(1000,2,.1))]:
    shape=cq.Solid.makeBox(*dims,cq.Vector(-dims[0]/2,-dims[1]/2,0));path=out/f'{name}.step'
    cq.exporters.export(shape,str(path))
    records.append(dict(path=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size,dimensions_mm=dims,units='mm'))
(out/'manifest.json').write_text(json.dumps(dict(schema_version=1,cases=records,tolerance=dict(length_absolute_mm=1e-6,volume_relative=1e-6),purpose='analytic B10 fixtures; no manufacturing truth claim'),indent=2)+'\n')
