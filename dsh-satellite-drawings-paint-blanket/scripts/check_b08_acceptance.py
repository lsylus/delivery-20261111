"""Archive real HTTP results plus independent analytic area and boundary checks."""
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import sys
import tempfile
from shapely.geometry import Polygon, Point

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/evidence/B08'
sys.path.insert(0,str(ROOT/'tests/paint'))
from http_case import Service, exercise
from b08_cases import assembly, params, classify_rib
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.domain.validation import validate


def record_file(path):
    data=path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    record=dict(status='fail',resources_created=[],resources_cleaned=[],analytic=[],artifacts=[])
    service=None
    try:
        for gap,count,status in [(0,2,'passed'),(.099,2,'passed'),(.1,0,'needs_review'),(.101,0,'passed')]:
            m=assembly(gap);result=generate(params(m),m,'analytic-'+str(gap))
            assert result['status']==status and len(result['regions'])==count
            area=sum(r['area_mm2'] for r in result['regions'])
            expected=count*(220+9*math.pi)
            assert math.isclose(area,expected,rel_tol=1e-6,abs_tol=1e-9)
            record['analytic'].append(dict(gap_mm=gap,status=status,region_count=count,area_mm2=area,expected_area_mm2=expected,
                decisions=result['evidence'],diagnostics=result['diagnostics']))
        m=assembly(features=True);p=params(m);classify_rib(m,p)
        result=generate(p,m,'analytic-features')
        assert result['status']=='passed'
        by_kind={r['kind']:r for r in result['regions']}
        assert math.isclose(by_kind['hole']['area_mm2'],33*math.pi,rel_tol=1e-6)
        assert math.isclose(by_kind['boss']['area_mm2'],16*math.pi,rel_tol=1e-6)
        record['features']=dict(hole_area_mm2=by_kind['hole']['area_mm2'],expected_hole_mm2=33*math.pi,
            boss_area_mm2=by_kind['boss']['area_mm2'],expected_boss_mm2=16*math.pi,boss_height_mm=by_kind['boss']['local_frame']['origin'][2],
            region_count=len(result['regions']),rib_protected=False)
        with tempfile.TemporaryDirectory(prefix='b08-acceptance-',dir=ROOT/'work') as temp:
            record['resources_created'].append(temp)
            service=Service(Path(temp)/'service',timeout=120)
            record['resources_created'].append('pid:'+str(service.process.pid))
            initial_pid=service.process.pid
            http,files=exercise(service)
            record['resources_cleaned'].append('pid:'+str(initial_pid))
            record['resources_created'].append('pid:'+str(service.process.pid))
            record['http']=http
            folder=OUT/'artifacts';folder.mkdir(exist_ok=True)
            for name,data in files.items():
                path=folder/name;path.write_bytes(data);record['artifacts'].append(record_file(path))
            paint=json.loads(files['paint-result.json'])
            validate('paint',paint,'PaintResult')
            validate('drawing',json.loads(files['drawing.json']))
            # Explicit drawing/overlay cross-check from downloaded bytes.
            hatches=[e for e in paint['drawing_document']['entities'] if e['kind']=='hatch']
            for region,hatch,overlay in zip(paint['regions'],hatches,paint['overlay'],strict=True):
                assert region['loops']==[hatch['outer_loop'],*hatch['holes']]
                assert region['id']==hatch['id']==overlay['region_id']
                poly=Polygon(region['loops'][0]['points'],[h['points'] for h in region['loops'][1:]])
                assert poly.is_valid and math.isclose(poly.area,region['area_mm2'],rel_tol=1e-12)
            last_pid=service.process.pid;service.close();service=None
            record['resources_cleaned'].append('pid:'+str(last_pid))
        record['resources_cleaned'].append(temp)
        record['status']='pass'
    finally:
        if service is not None:
            pid=service.process.pid;service.close();record['resources_cleaned'].append('pid:'+str(pid))
        (OUT/'acceptance.json').write_text(json.dumps(record,indent=2)+'\n')
    environment=dict(status='pass',python=sys.version,platform=platform.platform(),machine=platform.machine(),
        packages={n:importlib.metadata.version(n) for n in ('cadquery','cadquery-ocp','shapely','numpy','pytest','jsonschema','thermal-drawings-service')},
        tolerances='analytic length abs 1e-6 mm; area rel 1e-6; near zero abs 1e-9; not manufacturing tolerance')
    (OUT/'environment.json').write_text(json.dumps(environment,indent=2)+'\n')
    print(json.dumps(dict(status='pass',analytic_cases=4,real_http=True,artifact_count=len(record['artifacts']))))


if __name__=='__main__':main()
