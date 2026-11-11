"""Native preflight and B02 readback. Never substitute STEP fixtures for native conversion."""
from pathlib import Path
from dataclasses import asdict

from .capabilities import native_capability
from .manifest import verify_manifest


class NativeConversionUnavailable(RuntimeError):
    def __init__(self, capability):
        self.capability = capability
        self.code = capability['code']
        super().__init__(capability['reason'])


class NativeConverter:
    """B05 has no operational engine; configuration cannot enable untested adapters.

    This preflight is usable by the future B14 integration. Engine-specific
    transport/timeout/licensing must be implemented when an engine is selected.
    """
    def __init__(self, config=None):
        self.config = config or {}

    def probe(self, manifest):
        return native_capability(manifest, self.config)

    def convert(self, manifest, workdir):
        verify_manifest(Path(workdir), manifest)
        raise NativeConversionUnavailable(self.probe(manifest))


def inspect_step_geometry(path):
    """Worker-only readback; this establishes STEP facts, never native equivalence."""
    from geometry_core.serialization import read_step
    from geometry_core.xcaf import read_xcaf_source
    from OCP.BRepCheck import BRepCheck_Analyzer
    result = read_step(Path(path))
    if not result.shape.Faces() or not BRepCheck_Analyzer(result.shape.wrapped, True).IsValid():
        raise ValueError('STEP lacks nonempty valid B-rep faces')
    graph = read_xcaf_source(Path(path))
    nodes = [dict(key=n.key, parent=n.parent_key, children=list(n.child_keys),
                  occurrence_name=n.occurrence_name, definition_name=n.definition_name,
                  definition=n.definition_label_entry, local=asdict(n.local_transform),
                  world=asdict(n.world_transform)) for n in graph.nodes]
    return dict(status='readback_only', native_equivalence='not_verified',
                step=asdict(result.readback), roots=list(graph.root_keys), nodes=nodes,
                leaf_instances=sum(not n.child_keys for n in graph.nodes))
