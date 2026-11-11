"""Small analytic STEP assemblies for the simplified blanket workflow."""
from pathlib import Path
import hashlib
import json
import cadquery as cq

ROOT = Path(__file__).resolve().parents[1]


def build():
    output = ROOT / "fixtures/synthetic/simple-v1"
    output.mkdir(parents=True, exist_ok=True)
    cube = cq.Solid.makeBox(100, 100, 100, cq.Vector(-50, -50, 0))
    cylinder = cq.Solid.makeCylinder(40, 80)
    protrusion = cq.Solid.makeCylinder(10, 40, cq.Vector(0, 0, 100))
    cases = []
    for name, members in (
        ("cube", [("body", cube)]),
        ("cylinder", [("body", cylinder)]),
        ("cube-cylinder", [("body", cube), ("exposed-part", protrusion)]),
    ):
        assembly = cq.Assembly(name=name)
        for label, shape in members:
            assembly.add(shape, name=label)
        path = output / f"{name}.step"
        assembly.save(str(path))
        cases.append({
            "name": name, "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size, "units": "mm",
            "members": [label for label, _ in members],
            "intended_policy": "regular_cylinder_v1" if name == "cylinder" else "regular_box_v1",
            "excluded_member": "exposed-part" if name == "cube-cylinder" else None,
        })
    (output / "manifest.json").write_text(json.dumps({
        "purpose": "Analytic demonstration fixtures, independently selectable assembly members",
        "cases": cases,
        "expected": {"cube_dimensions_mm": [105, 105, 105],
                     "cylinder_diameter_height_mm": [84, 84],
                     "combination_body_dimensions_mm": [105, 105, 105],
                     "combination_exposed_cylinder_radius_mm": 10},
    }, indent=2) + "\n")
    print(json.dumps({"cases": cases}, indent=2))


if __name__ == "__main__":
    build()
