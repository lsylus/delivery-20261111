"""Neutral XCAF source graph types and STEP reader.

The graph describes the source assembly before either CAD or geometry applies
public identifiers, component selection, prototype grouping, or output policy.
"""

from __future__ import annotations

from collections.abc import Callable
import logging
from time import perf_counter
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping, TypeAlias

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TCollection import TCollection_AsciiString, TCollection_ExtendedString
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TDataStd import TDataStd_Name
from OCP.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
from OCP.TDocStd import TDocStd_Document
from OCP.TopLoc import TopLoc_Location
from OCP.XCAFDoc import XCAFDoc_DocumentTool

from geometry_core.transforms import (
    RigidTransform,
    rigid_transform_from_location,
)


XcafNodeKey: TypeAlias = tuple[int, ...]
XcafReadStage: TypeAlias = Literal["read", "transfer"]
XcafTransform = RigidTransform
_LOG = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class XcafReadOptions:
    """Presentation modes that may affect STEPCAF transfer cost."""

    read_names: bool = True
    read_colors: bool = True
    read_layers: bool = True
    read_metadata: bool = True


@dataclass(frozen=True, slots=True)
class XcafSourceNode:
    """One occurrence in deterministic depth-first source order."""

    key: XcafNodeKey
    parent_key: XcafNodeKey | None
    child_keys: tuple[XcafNodeKey, ...]
    depth: int
    occurrence_label_entry: str
    definition_label_entry: str
    occurrence_name: str
    definition_name: str
    is_reference: bool
    is_assembly: bool
    local_transform: XcafTransform
    world_transform: XcafTransform

    @property
    def is_leaf(self) -> bool:
        return not self.child_keys


@dataclass(frozen=True, slots=True)
class XcafNodeGeometry:
    """Native OCCT values for one neutral source node."""

    occurrence_shape: object
    definition_shape: object
    world_shape: object
    local_location: TopLoc_Location
    world_location: TopLoc_Location


@dataclass(frozen=True, slots=True)
class XcafSourceGraph:
    """Immutable graph metadata with native geometry held behind accessors."""

    source: Path
    source_sha256: str
    nodes: tuple[XcafSourceNode, ...]
    root_keys: tuple[XcafNodeKey, ...]
    _geometry_by_key: Mapping[XcafNodeKey, XcafNodeGeometry] = field(
        repr=False, compare=False
    )
    _document: object = field(repr=False, compare=False)
    source_length_units: tuple[str, ...] = ()
    _nodes_by_key: Mapping[XcafNodeKey, XcafSourceNode] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        nodes_by_key = {node.key: node for node in self.nodes}
        if len(nodes_by_key) != len(self.nodes):
            raise ValueError("XCAF source node keys must be unique")
        if set(nodes_by_key) != set(self._geometry_by_key):
            raise ValueError("every XCAF source node must have native geometry")
        for root_key in self.root_keys:
            if root_key not in nodes_by_key or nodes_by_key[root_key].parent_key is not None:
                raise ValueError("XCAF root keys must reference root nodes")
        for node in self.nodes:
            if node.parent_key is not None and node.parent_key not in nodes_by_key:
                raise ValueError("XCAF node parent is missing")
            for child_key in node.child_keys:
                child = nodes_by_key.get(child_key)
                if child is None or child.parent_key != node.key:
                    raise ValueError("XCAF child links must be bidirectional")
        object.__setattr__(self, "_nodes_by_key", MappingProxyType(nodes_by_key))
        object.__setattr__(
            self, "_geometry_by_key", MappingProxyType(dict(self._geometry_by_key))
        )

    def node(self, key: XcafNodeKey) -> XcafSourceNode:
        """Return one node by its source path key."""
        return self._nodes_by_key[key]

    def geometry(self, key: XcafNodeKey) -> XcafNodeGeometry:
        """Return native shapes and locations without exposing them in metadata."""
        return self._geometry_by_key[key]

    @property
    def leaves(self) -> tuple[XcafSourceNode, ...]:
        """Return leaf occurrences in the same deterministic source order."""
        return tuple(node for node in self.nodes if node.is_leaf)

    def occurrences_by_definition(self) -> Mapping[str, tuple[XcafNodeKey, ...]]:
        """Group occurrence paths by their neutral XCAF definition label."""
        groups: dict[str, list[XcafNodeKey]] = {}
        for node in self.nodes:
            groups.setdefault(node.definition_label_entry, []).append(node.key)
        return MappingProxyType(
            {definition: tuple(keys) for definition, keys in groups.items()}
        )


class XcafReadError(RuntimeError):
    """A reader failure with a stage that adapters can map to legacy errors."""

    def __init__(self, stage: str, message: str, *, status: str | None = None):
        super().__init__(message)
        self.stage = stage
        self.status = status


def label_name(label: TDF_Label) -> str:
    """Read a native Unicode name, trimming its ends; absent names are empty."""
    # Some OCP bindings crash when FindAttribute receives a missing GUID.
    if not label.IsAttribute(TDataStd_Name.GetID_s()):
        return ""
    attribute = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
        return attribute.Get().ToExtString().strip()
    return ""


# Keep the former internal entry point available to existing callers.
_label_name = label_name


def _label_entry(label: TDF_Label) -> str:
    entry = TCollection_AsciiString()
    TDF_Tool.Entry_s(label, entry)
    return entry.ToCString()


def _referred_label(shape_tool, label: TDF_Label) -> TDF_Label:
    if not shape_tool.IsReference_s(label):
        return label
    target = TDF_Label()
    if not shape_tool.GetReferredShape_s(label, target):
        raise XcafReadError("traverse", "XCAF reference has no target label")
    return target


def read_xcaf_source(
    source: Path,
    *,
    options: XcafReadOptions | None = None,
    on_stage: Callable[[XcafReadStage], None] | None = None,
) -> XcafSourceGraph:
    """Read a STEP/XCAF document into a policy-neutral source graph.

    The returned path keys are deterministic traversal coordinates, not public
    CAD or geometry identifiers. Definition label entries identify reusable
    prototypes without choosing either service's prototype policy.
    """
    source = Path(source).resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise XcafReadError("input", f"STEP file is missing or empty: {source}")
    from .serialization import validate_step_envelope
    validate_step_envelope(source)
    from .hashing import file_sha256
    source_hash = file_sha256(source)
    selected = options or XcafReadOptions()
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(selected.read_names)
    reader.SetColorMode(selected.read_colors)
    reader.SetLayerMode(selected.read_layers)
    if not selected.read_metadata:
        # Snapshot consumers retain names/geometry/assembly placements only.
        # Keep the general reader's default metadata behavior unchanged.
        for mode in ('GDT', 'Mat', 'Meta', 'Props', 'View', 'ProductMeta', 'SHUO'):
            getattr(reader, f'Set{mode}Mode')(False)
    if on_stage:
        on_stage("read")
    started = perf_counter()
    _LOG.info("STEP import read start bytes=%d", source.stat().st_size)
    status = reader.ReadFile(str(source))
    _LOG.info("STEP import read done seconds=%.3f", perf_counter()-started)
    if "RetDone" not in str(status):
        raise XcafReadError(
            "read", f"failed to read STEP/XCAF source: {status}", status=str(status)
        )
    # Capture source units on this reader before transfer changes target units.
    # A second full STEP parse/transfer is unnecessary for snapshot metadata.
    length_units = TColStd_SequenceOfAsciiString()
    reader.Reader().FileUnits(length_units, TColStd_SequenceOfAsciiString(), TColStd_SequenceOfAsciiString())
    source_length_units = tuple(length_units.Value(i).ToCString() for i in range(1, length_units.Length()+1))
    # Per-reader unit setting; never change platform/process global configuration.
    reader.ChangeReader().SetSystemLengthUnit(1.0)
    document = TDocStd_Document(TCollection_ExtendedString("xcaf-source"))
    if on_stage:
        on_stage("transfer")
    started = perf_counter()
    _LOG.info("STEP import transfer start")
    if not reader.Transfer(document):
        raise XcafReadError("transfer", "failed to transfer STEP/XCAF source")
    _LOG.info("STEP import transfer done seconds=%.3f", perf_counter()-started)
    started = perf_counter()
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    nodes_by_key: dict[XcafNodeKey, XcafSourceNode] = {}
    geometry_by_key: dict[XcafNodeKey, XcafNodeGeometry] = {}

    def visit(
        label: TDF_Label,
        key: XcafNodeKey,
        parent_key: XcafNodeKey | None,
        parent_location: TopLoc_Location,
    ) -> None:
        target = _referred_label(shape_tool, label)
        occurrence_shape = shape_tool.GetShape_s(label)
        if occurrence_shape.IsNull():
            raise XcafReadError("traverse", "null occurrence shape")
        if len(key) > 256:
            raise XcafReadError("traverse", "assembly depth exceeds 256 (cycle or unsupported depth)")
        local_location = occurrence_shape.Location()
        world_location = parent_location.Multiplied(local_location)
        children = TDF_LabelSequence()
        is_assembly = bool(shape_tool.IsAssembly_s(target))
        if is_assembly:
            shape_tool.GetComponents_s(target, children, False)
        child_keys = tuple((*key, index) for index in range(1, children.Length() + 1))
        geometry_by_key[key] = XcafNodeGeometry(
            occurrence_shape=occurrence_shape,
            definition_shape=shape_tool.GetShape_s(target),
            world_shape=occurrence_shape.Located(world_location),
            local_location=local_location,
            world_location=world_location,
        )
        nodes_by_key[key] = XcafSourceNode(
            key=key,
            parent_key=parent_key,
            child_keys=child_keys,
            depth=len(key) - 1,
            occurrence_label_entry=_label_entry(label),
            definition_label_entry=_label_entry(target),
            occurrence_name=_label_name(label),
            definition_name=_label_name(target),
            is_reference=bool(shape_tool.IsReference_s(label)),
            is_assembly=is_assembly,
            local_transform=rigid_transform_from_location(local_location),
            world_transform=rigid_transform_from_location(world_location),
        )
        for index in range(1, children.Length() + 1):
            visit(children.Value(index), (*key, index), key, world_location)

    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    if roots.Length() == 0:
        raise XcafReadError("transfer", "STEP has no free shapes")
    root_keys = tuple((index,) for index in range(1, roots.Length() + 1))
    for index, key in enumerate(root_keys, start=1):
        visit(roots.Value(index), key, None, TopLoc_Location())
    nodes = tuple(nodes_by_key[key] for key in sorted(nodes_by_key))
    _LOG.info("STEP import traversal done seconds=%.3f nodes=%d", perf_counter()-started, len(nodes))
    if file_sha256(source) != source_hash:
        raise XcafReadError("input_changed", "STEP input changed while reading")
    return XcafSourceGraph(
        source=source,
        source_sha256=source_hash,
        nodes=nodes,
        root_keys=root_keys,
        _geometry_by_key=geometry_by_key,
        _document=document,
        source_length_units=source_length_units,
    )
