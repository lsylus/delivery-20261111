"""Archive the four review counterexamples with measured, asserted outcomes."""
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tests/paint'))
from test_review_regressions import pocket_model, override_pair
from b08_cases import assembly,params,box,from_shapes,override
from thermal_drawings.paint.pipeline import generate
from thermal_drawings.paint.selection import Budget
from thermal_drawings.domain.validation import validate
from thermal_drawings.domain.errors import ServiceError
import geometry_core.solid_pairs as pairs


def main():
    record=dict(status='fail',review_commit='04698e786c70a5e0781791361103baf0e7e27fff',
                review_sha256=hashlib.sha256((ROOT/'docs/reviews/B08.md').read_bytes()).hexdigest(),threshold=[],openings=[])
    for gap,expected,count in [(.1-1e-7,'needs_review',0),(.1+1e-7,'needs_review',0),
                               (.1-1e-7-1e-9,'passed',2),(.1+1e-7+1e-9,'passed',0)]:
        m=assembly(gap);r=generate(params(m),m,'review-counterexample')
        assert r['status']==expected and len(r['regions'])==count
        record['threshold'].append(dict(gap_mm=gap,status=r['status'],regions=len(r['regions']),diagnostics=r['diagnostics']))
    for kind in ['blind','rectangular','back_pockets','through','counterbore','countersink']:
        m=pocket_model(kind);r=generate(params(m),m,'review-opening')
        assert r['status']==('needs_review' if kind in ('blind','rectangular','back_pockets') else 'passed')
        record['openings'].append(dict(kind=kind,status=r['status'],regions=[x['kind'] for x in r['regions']],evidence=r['evidence'],diagnostics=r['diagnostics']))
    m=pocket_model('blind');p=params(m)
    floor=next(r for o,f,r in m.faces if f.geomType()=='PLANE' and f.normalAt().z>.9 and abs(f.Center().z+2)<1e-6)
    p['overrides']=[override(floor,'hole')];r=generate(p,m,'review-exact-override')
    assert r['status']=='passed' and r['regions'][0]['origin']=='manual'
    record['manual_blind_policy']=dict(status=r['status'],override=p['overrides'][0],area_mm2=r['regions'][0]['area_mm2'])
    m=assembly();p=params(m);p['overrides']=override_pair(m)
    distinct=generate(p,m,'unused-record');assert distinct['status']=='needs_review'
    record['partial_override_application']=distinct['diagnostics']
    p['overrides'][1]['id']=p['overrides'][0]['id']
    try:validate('paint',p)
    except ServiceError as error:
        assert error.status==422;record['duplicate_id_http_status']=error.status
    else:raise AssertionError('duplicate override id accepted')
    model=from_shapes([box(0,0,-5,100,80,5)]+[box(5+18*i,10,.099,5,5,8) for i in range(5)])
    original=pairs.measure_planar_contact_area;scans=[]
    def counted(a,b,**kwargs):
        scans.append(len(a.Faces())*len(b.Faces()))
        return original(a,b,**kwargs)
    budget=Budget(maximum_pairs=100)
    with patch.object(pairs,'measure_planar_contact_area',counted):r=generate(params(model),model,'global-budget',budget=budget)
    assert r['status']=='needs_review' and not r['regions'] and r['drawing_document'] is None
    assert scans==[36,36] and sum(scans)<=budget.pairs<=100
    record['global_budget']=dict(limit=100,reserved_pairs=budget.pairs,actual_b03_scans=scans,actual_b03_pairs=sum(scans),status=r['status'],diagnostics=r['diagnostics'],partial_regions=len(r['regions']))
    record['status']='pass'
    output=ROOT/'docs/evidence/B08/review-regressions.json'
    output.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(status='pass',threshold_cases=len(record['threshold']),opening_cases=len(record['openings']),duplicate_id=422,budget=record['global_budget'])))


if __name__=='__main__':main()
