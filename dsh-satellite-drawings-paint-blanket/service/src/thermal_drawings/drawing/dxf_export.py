import json
import math
import os
from pathlib import Path
import tempfile

import ezdxf

from .document import DrawingDocument
from .profiles import DrawingProfile

APPID = "THERMAL_DRAWINGS"


class DrawingExporter:
    def write_dxf(self, document: DrawingDocument, destination, profile=DrawingProfile()):
        data = document.to_dict()
        doc = ezdxf.new(profile.dxf_version)
        doc.units = 4
        doc.header["$MEASUREMENT"] = 1
        doc.header["$LUNITS"] = 2
        doc.header["$INSBASE"] = (0, 0, 0)
        doc.linetypes.new("DASHED", dxfattribs={"pattern": [6.0, 4.0, -2.0]})
        doc.linetypes.new("CENTER", dxfattribs={"pattern": [10.0, 6.0, -1.0, 2.0, -1.0]})
        doc.styles.new("CJK", dxfattribs={"font": profile.font})
        doc.appids.new(APPID)
        metadata = doc.rootdict.add_xrecord(APPID)
        metadata.extend([(1, json.dumps({k: data[k] for k in ("id", "revision_id", "frame")}, ensure_ascii=True))])
        for layer in data["layers"]:
            doc.layers.new(layer["name"], dxfattribs={"color": layer["color"], "linetype": layer["line_type"]})
        space = doc.modelspace()
        for e in data["entities"]:
            attrs = {"layer": e["layer"]}
            kind = e["kind"]
            if kind == "line":
                item = space.add_line(e["start"], e["end"], dxfattribs=attrs)
            elif kind == "circle":
                item = space.add_circle(e["center"], e["radius_mm"], dxfattribs=attrs)
            elif kind == "arc":
                start, end = e["start_angle_rad"], e["end_angle_rad"]
                if e["direction"] == "cw":
                    start, end = end, start  # DXF ARC always runs CCW; XDATA preserves traversal.
                item = space.add_arc(e["center"], e["radius_mm"], math.degrees(start), math.degrees(end), dxfattribs=attrs)
            elif kind == "polyline":
                item = space.add_lwpolyline(e["points"], close=e["closed"], dxfattribs=attrs)
            elif kind == "hatch":
                item = space.add_hatch(dxfattribs=attrs)
                if e["pattern"] != "SOLID":
                    item.set_pattern_fill(e["pattern"], scale=1.0)
                item.dxf.hatch_style = 0  # Normal odd/even island detection.
                item.paths.add_polyline_path(e["outer_loop"]["points"], is_closed=True, flags=1)
                for hole in e["holes"]:
                    item.paths.add_polyline_path(hole["points"], is_closed=True, flags=0)
            elif kind == "text":
                item = space.add_text(e["text"], dxfattribs={**attrs, "insert": e["position"], "height": e["height_mm"], "style": "CJK"})
            elif kind == "point":
                item = space.add_point(e["position"], dxfattribs=attrs)
            elif kind == "dimension":
                a, b, p = e["start"], e["end"], e["position"]
                length = math.dist(a, b)
                distance = ((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])) / length
                dim = space.add_aligned_dim(a, b, distance=distance, text=e["text_override"] or "<>", dxfattribs=attrs,
                                            override={"dimtxt": 2.5, "dimasz": 2.5, "dimtxsty": "CJK", "dimlfac": 1.0})
                dim.render()
                item = dim.dimension
            else:
                raise ValueError(f"unsupported entity: {kind}")
            item.set_xdata(APPID, [(1000, e["id"]), (1000, data["revision_id"]), (1000, e.get("direction", ""))])
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=destination.parent, suffix=".dxf")
        os.close(fd)
        try:
            doc.saveas(temporary)
            from .validation import validate_dxf
            validate_dxf(document, temporary, profile)
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return destination
