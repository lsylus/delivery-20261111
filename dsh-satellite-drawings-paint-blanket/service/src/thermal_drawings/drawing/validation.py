"""Reparse actual DXF entities, including editable DIMENSION and HATCH islands."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

import ezdxf

from .profiles import DrawingProfile


def file_record(path):
    path = Path(path)
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size}


def validate_dxf(document, path, profile=DrawingProfile()):
    from .dxf_export import APPID
    expected = document.to_dict()
    doc = ezdxf.readfile(path)
    audit = doc.audit()
    if audit.errors or audit.fixes:
        raise ValueError("DXF audit errors or repairs required")
    if doc.units != 4 or doc.dxfversion != "AC1032":
        raise ValueError("DXF version/units mismatch")
    if doc.styles.get("CJK").dxf.font != profile.font:
        raise ValueError("font substitution")
    metadata = json.loads(doc.rootdict[APPID].tags[0].value)
    if metadata != {k: expected[k] for k in ("id", "revision_id", "frame")}:
        raise ValueError("document metadata mismatch")
    for layer in expected["layers"]:
        actual = doc.layers.get(layer["name"])
        if actual.dxf.color != layer["color"] or actual.dxf.linetype.upper() != layer["line_type"]:
            raise ValueError("layer profile mismatch")
    for name, pattern in {"DASHED": [6, 4, -2], "CENTER": [10, 6, -1, 2, -1]}.items():
        if any(layer["line_type"] == name for layer in expected["layers"]):
            values = [tag.value for tag in doc.linetypes.get(name).pattern_tags.tags if tag.code in (40, 49)]
            if values != pattern:
                raise ValueError("linetype dash lengths changed")
    space = list(doc.modelspace())
    if len(space) != len(expected["entities"]):
        raise ValueError("entity count mismatch")
    actual = {}
    for item in space:
        tags = item.get_xdata(APPID)
        if len(tags) != 3 or tags[1].value != expected["revision_id"] or tags[0].value in actual:
            raise ValueError("missing/duplicate entity identity or revision")
        actual[tags[0].value] = item

    def near(a, b):
        if isinstance(a, (list, tuple)):
            if len(a) != len(b):
                raise ValueError("coordinate dimension mismatch")
            for x, y in zip(a, b):
                near(x, y)
        elif not math.isfinite(float(b)) or abs(a-b) > profile.tolerance_mm:
            raise ValueError(f"numeric mismatch {a} != {b}")

    def xy(point):
        near(0, point.z)
        return [point.x, point.y]

    kinds = {"line": "LINE", "circle": "CIRCLE", "arc": "ARC", "polyline": "LWPOLYLINE",
             "hatch": "HATCH", "text": "TEXT", "dimension": "DIMENSION", "point": "POINT"}
    for e in expected["entities"]:
        item = actual[e["id"]]
        kind = e["kind"]
        if item.dxftype() != kinds[kind] or item.dxf.layer != e["layer"]:
            raise ValueError("entity type/layer mismatch")
        if kind in ("circle", "arc"):
            near(e["center"], xy(item.dxf.center))
            near(e["radius_mm"], item.dxf.radius)
            if kind == "arc":
                angles = [e["start_angle_rad"], e["end_angle_rad"]]
                if e["direction"] == "cw":
                    angles.reverse()
                for a, b in zip(angles, [item.dxf.start_angle, item.dxf.end_angle]):
                    near(0, math.remainder(a-math.radians(b), math.tau))
                if item.get_xdata(APPID)[2].value != e["direction"]:
                    raise ValueError("arc traversal changed")
        elif kind == "line":
            near(e["start"], xy(item.dxf.start)); near(e["end"], xy(item.dxf.end))
        elif kind == "polyline":
            near(e["points"], [list(p) for p in item.get_points("xy")])
            near(0, item.dxf.elevation)
            if bool(item.closed) != e["closed"] or item.has_arc or item.has_width:
                raise ValueError("polyline topology/width mismatch")
        elif kind == "hatch":
            loops = [e["outer_loop"], *e["holes"]]
            if len(item.paths) != len(loops) or item.dxf.hatch_style != 0 or item.dxf.pattern_name != e["pattern"]:
                raise ValueError("HATCH islands/style mismatch")
            for i, (loop, boundary) in enumerate(zip(loops, item.paths)):
                if not boundary.is_closed or bool(boundary.path_type_flags & 1) != (i == 0):
                    raise ValueError("HATCH external/hole flags mismatch")
                near(loop["points"], [[p[0], p[1]] for p in boundary.vertices])
                for p in boundary.vertices:
                    near(0, p[2])
        elif kind == "text":
            near(e["position"], xy(item.dxf.insert)); near(e["height_mm"], item.dxf.height)
            if item.dxf.text != e["text"] or item.dxf.style != "CJK":
                raise ValueError("text or CJK style changed")
        elif kind == "point":
            near(e["position"], xy(item.dxf.location))
        elif kind == "dimension":
            # ezdxf renders add_aligned_dim as a rotated linear DIMENSION (type 0).
            if item.dimtype != 0 or item.dxf.text != (e["text_override"] or "<>"):
                raise ValueError("editable aligned dimension lost")
            near(math.degrees(math.atan2(e["end"][1]-e["start"][1], e["end"][0]-e["start"][0])), item.dxf.angle)
            near(e["start"], xy(item.dxf.defpoint2)); near(e["end"], xy(item.dxf.defpoint3))
            near(math.dist(e["start"], e["end"]), item.get_measurement())
            a, b, p = e["start"], e["end"], e["position"]
            length = math.dist(a, b)
            distance = ((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])) / length
            q = xy(item.dxf.defpoint)
            near(distance, ((b[0]-a[0])*(q[1]-a[1])-(b[1]-a[1])*(q[0]-a[0]))/length)
            if not item.dxf.geometry or not list(doc.blocks[item.dxf.geometry]):
                raise ValueError("dimension display block missing")
    return {"status": "pass", "scope": "DXF structural/numeric readback only; not DWG/AutoCAD acceptance",
            "file": file_record(path), "entity_counts": dict(Counter(item.dxftype() for item in space)),
            "entity_count": len(space), "units": "mm", "tolerance_mm": profile.tolerance_mm,
            "audit_errors": 0, "audit_fixes": 0, "revision_id": expected["revision_id"]}
