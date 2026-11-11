"""Bounded audit of actual DWGs against native NetResult and fixed-point edits.

This reads delivered DWG bytes through OpenCADStudio --serve. Markers remain
POINT entities, never drilling holes. An optional second revision demonstrates
that a persistent point ID moved into both DrawingDocument and actual DWG.
No cover generation, parameter changes, export fabrication, or global profile edits.
"""
import argparse
from collections import Counter
import json
import hashlib
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "service/src"))
import ezdxf
from thermal_drawings.drawing.document import DrawingDocument
from thermal_drawings.drawing.opencadstudio import NativeSession, validate_opencad_readback
from thermal_drawings.drawing.validation import file_record

TOLERANCE = 1e-6


def load_net(path):
    value = json.loads(Path(path).read_text())
    if "drawing_document" in value and "fixed_points" in value:
        return value
    candidate = value.get("net", {})
    if "drawing_document" in candidate:
        return candidate
    if isinstance(candidate.get("net"), dict) and "drawing_document" in candidate["net"]:
        return candidate["net"]
    raise ValueError("Input must contain the actual NetResult with DrawingDocument")


def near(actual, expected, message):
    if len(actual) != len(expected) or any(
            not math.isfinite(float(a)) or abs(float(a)-float(b)) > TOLERANCE
            for a, b in zip(actual, expected)):
        raise ValueError(message + f": {actual} != {expected}")


def sheet_point(net, point):
    """Recompute both rigid maps directly, independently of backend drawing helpers."""
    panel = next(p for p in net["panels"] if p["key"] == point["panel_key"])
    transform = panel["transform"]
    uv = point["uv_mm"]
    unfolded = [sum(transform["rotation"][i][j]*uv[j] for j in range(2))
                + transform["translation"][i] for i in range(2)]
    near(point["net_uv_mm"], unfolded, "Persistent point net mapping mismatch")
    layout = next(p["layout"] for p in net["pieces"] if p["id"] == panel["piece_id"])
    angle = layout["rotation_rad"]
    c, s = math.cos(angle), math.sin(angle)
    result = [c*unfolded[0]-s*unfolded[1]+layout["translation_mm"][0],
              s*unfolded[0]+c*unfolded[1]+layout["translation_mm"][1]]
    return result


def point_audit(net, dxf_path):
    document = net["drawing_document"]
    source_points = [e for e in document["entities"] if e["kind"] == "point" and e["layer"] == "FIXING"]
    active = [p for p in net["fixed_points"] if p["status"] == "valid"]
    if len({p["id"] for p in active}) != len(active) or len(source_points) != len(active):
        raise ValueError("Persistent point identities or DrawingDocument marker count mismatch")
    dxf = ezdxf.readfile(dxf_path)
    actual = {}
    for entity in dxf.modelspace():
        if entity.dxftype() == "POINT" and entity.dxf.layer == "FIXING":
            tags = entity.get_xdata("THERMAL_DRAWINGS")
            if len(tags) != 3 or tags[1].value != net["revision_id"]:
                raise ValueError("DWG point revision/identity XDATA missing")
            if tags[0].value in actual:
                raise ValueError("Duplicate DWG point entity ID")
            actual[tags[0].value] = entity
    if len(actual) != len(active):
        raise ValueError("Actual DWG marker count mismatch")
    result = []
    used = set()
    for point in active:
        expected = sheet_point(net, point)
        matches = [e for e in source_points if math.dist(e["position"], expected) <= TOLERANCE]
        if len(matches) != 1 or matches[0]["id"] in used:
            raise ValueError("Point does not uniquely map into source DrawingDocument")
        source = matches[0]
        used.add(source["id"])
        entity = actual[source["id"]]
        dwg_xy = [entity.dxf.location.x, entity.dxf.location.y]
        near(dwg_xy, expected, "Actual DWG marker coordinate mismatch")
        near([entity.dxf.location.z], [0.], "Actual DWG marker not planar")
        result.append({"point_id": point["id"], "panel_key": point["panel_key"],
                       "panel_uv_mm": point["uv_mm"], "net_uv_mm": point["net_uv_mm"],
                       "drawing_entity_id": source["id"], "drawing_position_mm": source["position"],
                       "dwg_position_mm": dwg_xy, "semantics": "position_marker_POINT_not_drill_hole",
                       "maximum_coordinate_error_mm": max(abs(a-b) for a,b in zip(dwg_xy,expected))})
    return result


def verify_revision(label, net_path, dwg_path, output, config, required_terms):
    net = load_net(net_path)
    drawing = DrawingDocument(net["drawing_document"])
    if drawing.to_dict()["revision_id"] != net["revision_id"]:
        raise ValueError("Net and DrawingDocument revisions differ")
    dwg = Path(dwg_path).resolve()
    if dwg.read_bytes()[:6] != b"AC1032":
        raise ValueError("Expected actual DWG 2018 bytes")
    raw, validated = output / (label+".readback.dxf"), output / (label+".validated.dxf")
    # A private profile and temporary stderr/config files; no shared native session.
    with tempfile.TemporaryDirectory(prefix=".native-point-audit-", dir=output) as work:
        session = NativeSession(config["executable"], work, config.get("timeout_s",30))
        try:
            session.call({"op":"open","path":str(dwg)})
            state = session.call({"protocol":1,"op":"state"})
            audit = session.call({"protocol":1,"op":"audit","target_format":"dwg","target_version":"2018"})
            saved = session.verified_save(raw,"dxf")
            version = session.greeting["version"]
        finally:
            session.close()
    if state.get("missing_fonts"):
        raise ValueError("Native software reports missing fonts")
    readback = validate_opencad_readback(drawing,raw,validated)
    selected = validated if validated.exists() else raw
    points = point_audit(net,selected)
    doc = ezdxf.readfile(selected)
    texts = [e.dxf.text for e in doc.modelspace() if e.dxftype()=="TEXT"]
    for term in required_terms:
        if not any(term in text for text in texts):
            raise ValueError("Required feature label/text absent from actual DWG: "+term)
    dimensions = [{"entity_id":e.get_xdata("THERMAL_DRAWINGS")[0].value,
                   "measurement_mm":e.get_measurement(),"text":e.dxf.text}
                  for e in doc.modelspace() if e.dxftype()=="DIMENSION"]
    cut = Counter(e.dxftype() for e in doc.modelspace() if e.dxf.layer=="CUT")
    if not cut:
        raise ValueError("Actual drawing has no cutting contours")
    cut_shapes = [{k:v for k,v in e.items() if k not in ("id","source_refs")}
                  for e in drawing.to_dict()["entities"] if e["layer"]=="CUT"]
    cut_signature = hashlib.sha256(json.dumps(cut_shapes,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()
    summary = net.get("manufacturing_summary", {})
    return {"status":"passed","source_net":file_record(net_path),"dwg":file_record(dwg),
            "revision_id":net["revision_id"],"native_version":version,"native_audit":audit,
            "native_reverse_verified":saved["verified"],"strict_readback":readback,
            "contours_by_type":dict(cut),"source_cut_geometry_sha256":cut_signature,"text_values":texts,"required_terms":required_terms,
            "editable_dimensions":dimensions,"fixed_point_count":len(points),"fixed_points":points,
            "actual_piece_count_per_layer":len(net["pieces"]),"manufacturing_summary":summary,
            "piece_limit_exceeded":bool(summary.get("requirements_unmet")),
            "native_fixed_point_semantics":"position markers; no drilling operation inferred"}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--net",required=True)
    parser.add_argument("--dwg",required=True)
    parser.add_argument("--output",required=True,type=Path)
    parser.add_argument("--config",default=str(ROOT/"deploy/opencadstudio-5090.json"))
    parser.add_argument("--previous-net")
    parser.add_argument("--previous-dwg")
    parser.add_argument("--point-id",help="Persistent moved point ID; required when two revisions are compared")
    parser.add_argument("--require-text",action="append",default=[])
    args=parser.parse_args()
    if bool(args.previous_net)!=bool(args.previous_dwg):
        parser.error("Both previous paths are required together")
    if args.previous_net and not args.point_id:
        parser.error("--point-id is required to prove the intended point movement")
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    config=json.loads(Path(args.config).read_text())["dwg"]
    report={"status":"failed","scope":"Execution-side independent coordinate audit using actual native DWG readback; not independent CAD certification"}
    try:
        current=verify_revision("after",args.net,args.dwg,output,config,args.require_text)
        report["after"]=current
        if args.previous_net:
            previous=verify_revision("before",args.previous_net,args.previous_dwg,output,config,[])
            report["before"]=previous
            def chosen(revision):
                return next(p for p in revision["fixed_points"] if p["point_id"]==args.point_id)
            if previous["source_cut_geometry_sha256"] != current["source_cut_geometry_sha256"]:
                raise ValueError("Moving a position marker changed cutting geometry; inspect the revisions")
            a,b=chosen(previous),chosen(current)
            delta=[b["dwg_position_mm"][i]-a["dwg_position_mm"][i] for i in range(2)]
            if math.hypot(*delta)<=TOLERANCE:
                raise ValueError("The intended marker did not move in actual DWG")
            expected=[b["drawing_position_mm"][i]-a["drawing_position_mm"][i] for i in range(2)]
            near(delta,expected,"DWG displacement differs from source DrawingDocument")
            report["moved_point"]={"point_id":args.point_id,"before":a,"after":b,
                                   "dwg_delta_mm":delta,"drawing_delta_mm":expected,
                                   "cut_geometry_unchanged":True}
        report["status"]="passed"
    except Exception as error:
        report["error"]={"type":type(error).__name__,"message":str(error)}
        raise
    finally:
        (output/"native-dwg-audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"status":report["status"],"report":str(output/"native-dwg-audit.json")},ensure_ascii=False))


if __name__=="__main__":
    main()
