from decimal import Decimal
from pathlib import Path
import copy
import json

import pytest
import ezdxf
from heater_drawing.drawing.leads import lead_parameters
from heater_drawing.drawing.sample import _plan_page
from heater_drawing.drawing.dxf_writer import write_page_dxf
from heater_drawing.drawing.readback import inspect_dxf, ReadbackError, _validate_lead_dimension_clearance
from heater_drawing.drawing.template import load_template

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("size,expected", [("0.5", ("0.30", "0.175", "3")), ("25", ("6.25", "5", "6.25")), ("50", ("12", "10", "12")), ("1000", ("12", "10", "12"))])
def test_leads_follow_paper_short_edge_with_caps(size, expected):
    profile = load_template(ROOT / "templates/heater-a4-v1")["layout"]["lead_parameters_paper_mm"]
    for denominator in (Decimal(1), Decimal(2), Decimal(10)):
        values = lead_parameters(Decimal(size)*denominator, Decimal(size)*2*denominator, denominator, profile)
        assert tuple(values.values()) == tuple(map(Decimal, expected))


@pytest.mark.parametrize("short,long,scale,side", [("0.5","1","1","short"),("2","5","2","long"),("25","25","1","short"),("30","50","1","long"),("100","300","2","short"),("200","600","5","long"),("500","1200","10","short")])
def test_small_large_and_scaled_leads_read_back_inside_drawing(tmp_path, short, long, scale, side):
    template = load_template(ROOT / "templates/heater-a4-v1")
    data = json.loads((ROOT / "fixtures/synthetic/heater_sample.json").read_text(encoding="utf-8"))
    row = copy.deepcopy(data["rows"][0]);row["fields"].update(code="RULE-CHECK",width_mm=short,length_mm=long,requested_scale="1:"+scale,lead_side=side)
    page = _plan_page(row, template["layout"], "a"*64, template["template_sha256"])
    output = tmp_path / "rule.dxf"
    write_page_dxf(output, page, template["layout"], template["fonts"])
    if short == "0.5":
        # 0.18 mm strokes need more clearance than this tiny paper outline.
        with pytest.raises(ReadbackError, match="lead/dimension clearance"):
            inspect_dxf(output, [page], template["layout"], template["fonts"])
    else:
        result = inspect_dxf(output, [page], template["layout"], template["fonts"])
        assert result["status"] == "passed"


def test_oversize_page_fails_instead_of_accepting_out_of_bounds_leads(tmp_path):
    template = load_template(ROOT / "templates/heater-a4-v1")
    row = json.loads((ROOT / "fixtures/synthetic/heater_sample.json").read_text(encoding="utf-8"))["rows"][0]
    row["fields"].update(code="OVERSIZE",width_mm="150",length_mm="300",requested_scale="1:1")
    page = _plan_page(row, template["layout"], "a"*64, template["template_sha256"])
    output = tmp_path / "oversize.dxf";write_page_dxf(output,page,template["layout"],template["fonts"])
    with pytest.raises(ReadbackError, match="bounds leave drawing area|collision"):
        inspect_dxf(output,[page],template["layout"],template["fonts"])


def test_clearance_checks_rendered_strokes_and_text_separately():
    doc=ezdxf.new('R2018');msp=doc.modelspace()
    leads=[msp.add_line((x,0),(x,10)) for x in (0,2)]
    safe=msp.add_linear_dim(base=(0,20),p1=(-10,0),p2=(12,0));safe.render()
    assert _validate_lead_dimension_clearance(leads,[safe.dimension],{},1,0)>0.25
    crossing=msp.add_linear_dim(base=(0,5),p1=(-10,0),p2=(12,0));crossing.render()
    with pytest.raises(ReadbackError,match='clearance'):
        _validate_lead_dimension_clearance(leads,[crossing.dimension],{},1,0)
    with pytest.raises(ReadbackError,match='clearance'):
        _validate_lead_dimension_clearance(leads,[safe.dimension],{'text':{'box_paper_mm':[-1,3,1,6]}},1,0)
