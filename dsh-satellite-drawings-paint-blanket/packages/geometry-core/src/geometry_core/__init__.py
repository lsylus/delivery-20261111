"""Independent OCCT geometry; invoke in isolated workers, not HTTP threads."""
from .snapshot import load_model_snapshot
from .tessellation import tessellate_with_face_map
from .xcaf import read_xcaf_source, XcafReadOptions, XcafReadError

__all__ = ["load_model_snapshot", "tessellate_with_face_map", "read_xcaf_source", "XcafReadOptions", "XcafReadError"]
