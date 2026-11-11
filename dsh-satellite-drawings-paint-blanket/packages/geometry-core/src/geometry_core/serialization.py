"""Policy-neutral STEP shape writing and parser readback facts."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import cadquery as cq
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPControl import STEPControl_Reader
from OCP.TColStd import TColStd_SequenceOfAsciiString

from geometry_core.bounds import (
    BoundsStrategy,
    ShapeBounds,
    measure_shape_bounds,
)
from geometry_core.topology import ShapeTopology, measure_shape_topology
from geometry_core.hashing import file_sha256


_FILE_SCHEMA = re.compile(rb"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", re.I)


class StepReadError(ValueError):
    """A STEP file could not produce one transferable OCCT shape."""


StepTopology = ShapeTopology


@dataclass(frozen=True, slots=True)
class StepReadback:
    """Immutable file and geometry facts with no service publication policy."""

    completed: bool
    volume_mm3: float
    byte_count: int
    sha256: str
    schema: str | None
    length_units: tuple[str, ...]
    transferred_root_count: int
    shape_count: int
    bounds: ShapeBounds
    topology: StepTopology


@dataclass(frozen=True, slots=True)
class StepReadResult:
    """One parsed shape and its neutral readback summary."""

    shape: cq.Shape = field(repr=False, compare=False)
    readback: StepReadback


def _sequence_values(values: TColStd_SequenceOfAsciiString) -> tuple[str, ...]:
    result = []
    for index in range(1, values.Length() + 1):
        value = values.Value(index)
        result.append(
            value.ToCString() if hasattr(value, "ToCString") else str(value)
        )
    return tuple(result)


def _step_schema(path: Path) -> str | None:
    with path.open("rb") as source:
        header = source.read(256 * 1024)
    matched = _FILE_SCHEMA.search(header)
    return matched.group(1).decode("latin-1") if matched else None


def _topology(shape) -> StepTopology:
    return measure_shape_topology(shape)


def read_step(path: Path) -> StepReadResult:
    """Parse a STEP file once and return its shape plus neutral source facts."""
    source = path.resolve()
    if not source.is_file() or source.stat().st_size <= 0:
        raise StepReadError(f"STEP file is missing or empty: {source}")

    validate_step_envelope(source)
    reader = STEPControl_Reader()
    if reader.ReadFile(str(source)) != IFSelect_RetDone:
        raise StepReadError(f"failed to read STEP: {source.name}")

    length_units = TColStd_SequenceOfAsciiString()
    angle_units = TColStd_SequenceOfAsciiString()
    solid_angle_units = TColStd_SequenceOfAsciiString()
    reader.FileUnits(length_units, angle_units, solid_angle_units)
    reader.SetSystemLengthUnit(1.0)
    transferred_roots = int(reader.TransferRoots())
    if transferred_roots <= 0:
        raise StepReadError(f"STEP has no transferable roots: {source.name}")
    native_shape = reader.OneShape()
    if native_shape.IsNull():
        raise StepReadError(f"STEP produced a null shape: {source.name}")

    shape = cq.Shape.cast(native_shape)
    readback = StepReadback(
        completed=True,
        volume_mm3=sum(s.Volume() for s in shape.Solids()),
        byte_count=source.stat().st_size,
        sha256=file_sha256(source),
        schema=_step_schema(source),
        length_units=_sequence_values(length_units),
        transferred_root_count=transferred_roots,
        shape_count=int(reader.NbShapes()),
        bounds=measure_shape_bounds(
            native_shape,
            strategy=BoundsStrategy.OPTIMAL_WITHOUT_SHAPE_TOLERANCE,
        ),
        topology=_topology(native_shape),
    )
    return StepReadResult(shape=shape, readback=readback)


def read_step_summary(path: Path) -> StepReadback:
    """Parse one STEP file and return only its immutable readback facts."""
    return read_step(path).readback


def write_step_shape(shape, destination: Path) -> Path:
    """Write one shape as STEP without imposing publication or readback policy."""
    target = destination.resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    native_shape = shape.wrapped if isinstance(shape, cq.Shape) else shape
    wrapped = cq.Shape.cast(native_shape)
    if wrapped.wrapped.IsNull():
        raise ValueError("cannot write a null STEP shape")
    cq.exporters.export(wrapped, str(target), exportType="STEP")
    if not target.is_file() or target.stat().st_size <= 0:
        raise RuntimeError(f"STEP writer produced no output: {target}")
    return target

def validate_step_envelope(path: Path) -> None:
    raw = Path(path).read_bytes()
    if not raw.lstrip().startswith(b"ISO-10303-21;") or not raw.rstrip().endswith(b"END-ISO-10303-21;"):
        raise StepReadError("missing STEP envelope/footer (empty, corrupt or truncated file)")
    # OCP 7.9's ExternFiles map is not Python-bound. Reject external-document
    # entities before native transfer can read unmanifested paths. Conservative:
    # an attached DOCUMENT_FILE is rejected even if it is not shape-bearing.
    if re.search(rb"\b(?:DOCUMENT_FILE|EXTERNALLY_DEFINED_REPRESENTATION)\s*\(", raw, re.I):
        raise StepReadError("external STEP document references require a verified multi-file manifest")

def inspect_step(path: Path) -> dict:
    """Serializable success/failure status; a failed parse never becomes empty geometry."""
    from dataclasses import asdict
    try:
        return asdict(read_step_summary(Path(path)))
    except (ValueError, RuntimeError, OSError) as exc:
        return {"completed": False, "error": str(exc)}

def write_step_graph(graph, destination: Path) -> Path:
    """Export the retained source document, including every root and occurrence."""
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    target = Path(destination).resolve()
    if target == graph.source:
        raise ValueError("source geometry is read-only")
    target.parent.mkdir(parents=True, exist_ok=True)
    writer = STEPCAFControl_Writer()
    writer.SetNameMode(True); writer.SetColorMode(True); writer.SetLayerMode(True)
    if not writer.Transfer(graph._document, STEPControl_AsIs) or writer.Write(str(target)) != IFSelect_RetDone:
        raise RuntimeError("STEPCAF export failed")
    read_step_summary(target)
    return target
