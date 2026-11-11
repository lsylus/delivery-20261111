"""Export and inspect real DXFs across short edges, scales and lead directions."""
from pathlib import Path
from decimal import Decimal
import argparse, copy, hashlib, json, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'service/src'))
from heater_drawing.drawing.sample import _plan_page
from heater_drawing.drawing.template import load_template
from heater_drawing.drawing.dxf_writer import write_page_dxf
from heater_drawing.drawing.readback import inspect_dxf, ReadbackError
from heater_drawing.drawing.leads import lead_parameters

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    out=(ROOT/args.output).resolve();out.mkdir(parents=True,exist_ok=True)
    template=load_template(ROOT/'templates/heater-a4-v1')
    seed=json.loads((ROOT/'fixtures/synthetic/heater_sample.json').read_text(encoding='utf-8'))['rows'][0]
    cases=[('0.5','1','1','short',True),('2','5','2','long',False),('25','25','1','short',False),
           ('30','50','1','long',False),('100','300','2','short',False),('200','600','5','long',False),
           ('500','1200','10','short',False),('12.5','37.5','1','short',False),
           ('150','250','5','long',False),('25','25','1','long',False),('150','300','1','short',True)]
    results=[];hashes={}
    for i,(w,l,n,side,reject) in enumerate(cases):
        row=copy.deepcopy(seed);row['fields'].update(code=f'RULE-{i}',width_mm=w,length_mm=l,requested_scale='1:'+n,lead_side=side)
        page=_plan_page(row,template['layout'],'a'*64,template['template_sha256'])
        path=out/f'lead-matrix/{i:02}.dxf';write_page_dxf(path,page,template['layout'],template['fonts'])
        result={'width_mm':w,'length_mm':l,'scale':'1:'+n,'lead_side':side,'paper_short_edge_mm':str(Decimal(w)/Decimal(n)),
                'parameters_paper_mm':{k:str(v) for k,v in lead_parameters(Decimal(w),Decimal(l),Decimal(n),template['layout']['lead_parameters_paper_mm']).items()},
                'path':path.relative_to(ROOT).as_posix()}
        try:
            readback=inspect_dxf(path,[page],template['layout'],template['fonts'])
            assert not reject,'expected unsafe paper geometry to be rejected'
            result.update(status='passed',readback=readback)
        except ReadbackError as exc:
            if not reject:raise
            assert 'clearance below' in str(exc) or 'bounds leave drawing area' in str(exc) or 'collision' in str(exc)
            result.update(status='rejected_as_expected',reason=str(exc))
        hashes[result['path']]=hashlib.sha256(path.read_bytes()).hexdigest();results.append(result)
    # Same paper dimensions must retain identical lengths, independent of code and scale.
    assert results[3]['parameters_paper_mm']==results[8]['parameters_paper_mm']
    assert results[2]['parameters_paper_mm']==results[9]['parameters_paper_mm']
    payload={'status':'passed','rule_id':'short-edge-paper-v1','minimum_dimension_clearance_paper_mm':.25,
             'same_paper_size_invariance':True,'square_direction_invariance':True,'cases':results,'artifact_hashes':hashes}
    (out/'lead-matrix.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':'passed','cases':len(results),'accepted':sum(c['status']=='passed' for c in results),'rejected':sum(c['status']=='rejected_as_expected' for c in results)},indent=2))
    return 0
if __name__=='__main__':raise SystemExit(main())
