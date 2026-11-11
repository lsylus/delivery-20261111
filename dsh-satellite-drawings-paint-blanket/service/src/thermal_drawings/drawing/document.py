"""Schema-backed immutable-by-copy document; coordinates are drawing-local millimetres."""
import copy
import json
import math
from pathlib import Path

from jsonschema import Draft202012Validator
from shapely.geometry import Polygon


def _finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non-finite coordinate")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    if isinstance(value, list):
        for item in value:
            _finite(item)


def _loop(loop):
    points = loop["points"]
    polygon = Polygon(points)
    if not polygon.is_valid or polygon.area <= 0:
        raise ValueError("invalid/degenerate/self-intersecting loop")
    signed = sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(points, points[1:]+points[:1]))
    if (signed > 0) != (loop["orientation"] == "ccw"):
        raise ValueError("loop orientation disagrees with vertices")
    return polygon


class DrawingDocument:
    def __init__(self, data):
        schema = json.loads(Path(__file__).with_name("drawing.schema.json").read_text())
        Draft202012Validator(schema).validate(data)
        _finite(data)
        axes = [data["frame"][key] for key in ("x_axis", "y_axis", "z_axis")]
        for i in range(3):
            for j in range(3):
                if abs(sum(a*b for a, b in zip(axes[i], axes[j])) - (i == j)) > 1e-9:
                    raise ValueError("non-orthonormal frame")
        x, y, z = axes
        cross = [x[1]*y[2]-x[2]*y[1], x[2]*y[0]-x[0]*y[2], x[0]*y[1]-x[1]*y[0]]
        if any(abs(a-b) > 1e-9 for a, b in zip(cross, z)):
            raise ValueError("left-handed frame")
        layers = [layer["name"] for layer in data["layers"]]
        ids = [entity["id"] for entity in data["entities"]]
        if len(set(layers)) != len(layers) or len(set(ids)) != len(ids):
            raise ValueError("duplicate layer/entity ID")
        if not ids:
            raise ValueError("empty drawing cannot be exported")
        for layer in data["layers"]:
            if layer["line_type"] not in ("CONTINUOUS", "DASHED", "CENTER"):
                raise ValueError("unsupported linetype")
        for entity in data["entities"]:
            if entity["layer"] not in layers:
                raise ValueError("undeclared layer")
            kind = entity["kind"]
            if kind in ("line", "dimension") and entity["start"] == entity["end"]:
                raise ValueError("zero-length line/dimension")
            if kind == "arc" and math.isclose((entity["end_angle_rad"]-entity["start_angle_rad"]) % math.tau, 0, abs_tol=1e-12):
                raise ValueError("zero/full-circle arc must use circle")
            if kind == "polyline":
                points = entity["points"]
                if any(a == b for a, b in zip(points, points[1:])):
                    raise ValueError("duplicate consecutive vertex")
                if entity["closed"] and (len(points) < 3 or not Polygon(points).is_valid or Polygon(points).area == 0):
                    raise ValueError("invalid closed polyline")
            if kind == "hatch":
                if entity["pattern"] not in ("SOLID", "ANSI31"):
                    raise ValueError("unsupported hatch pattern")
                outer = _loop(entity["outer_loop"])
                holes = [_loop(loop) for loop in entity["holes"]]
                if any(not outer.contains(hole) or outer.boundary.intersects(hole.boundary) for hole in holes):
                    raise ValueError("hole must lie strictly inside outer ring")
                if any(a.intersects(b) for i, a in enumerate(holes) for b in holes[i+1:]):
                    raise ValueError("overlapping/nested holes")
            if kind == "text" and any(c in entity["text"] for c in ("\n", "\r", "\x00")):
                raise ValueError("B04 TEXT supports a single line only")
        self._data = copy.deepcopy(data)

    @classmethod
    def read(cls, path):
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def to_dict(self):
        return copy.deepcopy(self._data)
