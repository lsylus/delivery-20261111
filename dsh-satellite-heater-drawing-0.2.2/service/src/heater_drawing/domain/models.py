"""Versioned domain structures shared by later batches."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Annotated, Any, Literal, Mapping
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    Strict,
    StrictBool,
    WithJsonSchema,
    field_validator,
    model_validator,
)

ASCII_DECIMAL_PATTERN = (
    r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$(?![\s\S])"
)
SIGNED_ASCII_DECIMAL_PATTERN = (
    r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$(?![\s\S])"
)
POSITIVE_ASCII_DECIMAL_PATTERN = (
    r"^(?:0\.[0-9]*[1-9][0-9]*|[1-9][0-9]*(?:\.[0-9]+)?)$(?![\s\S])"
)
SCALE_DENOMINATOR_PATTERN = (
    r"^(?:1(?:\.[0-9]+)?|(?:[2-9]|[1-9][0-9]+)(?:\.[0-9]+)?)$(?![\s\S])"
)
SCALE_LABEL_PATTERN = (
    r"^1:(?:1(?:\.[0-9]+)?|(?:[2-9]|[1-9][0-9]+)(?:\.[0-9]+)?)$(?![\s\S])"
)
ROW_ID_PATTERN = r"^[^:\r\n]+:(?:[2-9]|[1-9][0-9]+)$(?![\s\S])"
SHA256_PATTERN = r"^[0-9a-f]{64}$(?![\s\S])"
SAFE_RELATIVE_PATH_PATTERN = (
    r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\)[\s\S]+$(?![\s\S])"
)


def _fullmatch(pattern: str, value: str, label: str) -> str:
    if re.fullmatch(pattern.replace(r"$(?![\s\S])", ""), value, flags=re.ASCII) is None:
        raise ValueError(f"{label} has invalid syntax")
    return value


def _decimal(value: str) -> str:
    return _fullmatch(
        ASCII_DECIMAL_PATTERN,
        value,
        "decimal string",
    )


def _signed_decimal(value: str) -> str:
    return _fullmatch(
        SIGNED_ASCII_DECIMAL_PATTERN,
        value,
        "signed decimal string",
    )


def _positive_decimal(value: str) -> str:
    return _fullmatch(
        POSITIVE_ASCII_DECIMAL_PATTERN,
        value,
        "positive decimal string",
    )


def _scale_denominator(value: str) -> str:
    _fullmatch(SCALE_DENOMINATOR_PATTERN, value, "scale denominator")
    if Decimal(value) < 1:
        raise ValueError("scale denominator must be at least 1")
    return value


def _scale_label(value: str) -> str:
    _fullmatch(SCALE_LABEL_PATTERN, value, "scale label")
    return value


def _row_id(value: str) -> str:
    return _fullmatch(ROW_ID_PATTERN, value, "row_id")


def _sha256(value: str) -> str:
    return _fullmatch(SHA256_PATTERN, value, "SHA-256")


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or ".." in path.parts
    ):
        raise ValueError("relative_path must be a safe POSIX relative path")
    return value


DecimalString = Annotated[
    str,
    Strict(),
    AfterValidator(_decimal),
    WithJsonSchema({"type": "string", "pattern": ASCII_DECIMAL_PATTERN}),
]
SignedDecimalString = Annotated[
    str,
    Strict(),
    AfterValidator(_signed_decimal),
    WithJsonSchema({"type": "string", "pattern": SIGNED_ASCII_DECIMAL_PATTERN}),
]
PositiveDecimalString = Annotated[
    str,
    Strict(),
    AfterValidator(_positive_decimal),
    WithJsonSchema(
        {"type": "string", "pattern": POSITIVE_ASCII_DECIMAL_PATTERN}
    ),
]
ScaleDenominatorString = Annotated[
    str,
    Strict(),
    AfterValidator(_scale_denominator),
    WithJsonSchema({"type": "string", "pattern": SCALE_DENOMINATOR_PATTERN}),
]
ScaleLabelString = Annotated[
    str,
    Strict(),
    AfterValidator(_scale_label),
    WithJsonSchema({"type": "string", "pattern": SCALE_LABEL_PATTERN}),
]
Sha256 = Annotated[
    str,
    Strict(),
    AfterValidator(_sha256),
    WithJsonSchema({"type": "string", "pattern": SHA256_PATTERN}),
]
RowId = Annotated[
    str,
    Strict(),
    AfterValidator(_row_id),
    WithJsonSchema({"type": "string", "pattern": ROW_ID_PATTERN}),
]
SafeRelativePath = Annotated[
    str,
    Strict(),
    AfterValidator(_safe_relative_path),
    WithJsonSchema(
        {"type": "string", "minLength": 1, "pattern": SAFE_RELATIVE_PATH_PATTERN}
    ),
]
StrictExcelRow = Annotated[int, Field(strict=True, ge=2)]
StrictNonNegativeInt = Annotated[int, Field(strict=True, ge=0)]
StrictPositiveInt = Annotated[int, Field(strict=True, ge=1)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class LeadSide(StrEnum):
    SHORT = "short"
    LONG = "long"


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class IssueScope(StrEnum):
    WORKBOOK = "workbook"
    ROW = "row"
    SYSTEM = "system"


class DecisionKind(StrEnum):
    SCALE = "scale"
    SKIP = "skip"


class ArtifactKind(StrEnum):
    DXF = "dxf"
    DWG = "dwg"
    PDF_SINGLE = "pdf_single"
    PDF_MERGED = "pdf_merged"
    EXCEL_ORIGINAL = "excel_original"
    EXCEL_ACTUAL = "excel_actual"
    REPORT = "report"
    MANIFEST = "manifest"
    ZIP = "zip"


class ErrorCode(StrEnum):
    """Fixed v1 vocabulary shared by row issues and HTTP errors."""

    INVALID_REQUEST = "INVALID_REQUEST"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    ACCESS_DENIED = "ACCESS_DENIED"
    NOT_FOUND = "NOT_FOUND"
    REVISION_CONFLICT = "REVISION_CONFLICT"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    INVALID_FIELD = "INVALID_FIELD"
    MISSING_FIELD = "MISSING_FIELD"
    DUPLICATE_CODE = "DUPLICATE_CODE"
    WORKER_INTERRUPTED = "WORKER_INTERRUPTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class SourceLocation(StrictModel):
    sheet: str = Field(min_length=1, max_length=128)
    excel_row: StrictExcelRow


class HeaterFields(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=1, max_length=256)
    width_mm: PositiveDecimalString
    length_mm: PositiveDecimalString
    lead_side: LeadSide
    resistance_ohm: PositiveDecimalString
    tolerance_ohm: DecimalString
    quantity_text: str = Field(min_length=1, max_length=256)
    requested_scale: Annotated[ScaleLabelString, Field(max_length=256)]
    organization: str = Field(min_length=1, max_length=256)
    model: str = Field(min_length=1, max_length=256)
    designer: str = Field(min_length=1, max_length=256)
    checker: str = Field(min_length=1, max_length=256)
    reviewer: str = Field(min_length=1, max_length=256)
    standards_reviewer: str = Field(min_length=1, max_length=256)
    approver: str = Field(min_length=1, max_length=256)
    stage: str = Field(min_length=1, max_length=256)


class RawHeaterFields(StrictModel):
    name: Any
    code: Any
    width_mm: Any
    length_mm: Any
    lead_side: Any
    resistance_ohm: Any
    tolerance_ohm: Any
    quantity_text: Any
    requested_scale: Any
    organization: Any
    model: Any
    designer: Any
    checker: Any
    reviewer: Any
    standards_reviewer: Any
    approver: Any
    stage: Any


class ImportedHeaterRow(StrictModel):
    """A source row retained before field validation succeeds."""

    schema_version: Literal[1] = 1
    row_id: RowId
    source: SourceLocation
    raw: RawHeaterFields
    cell_types: dict[str, str] = Field(default_factory=dict)

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_strict_one(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def row_id_matches_source(self) -> "ImportedHeaterRow":
        if self.row_id != f"{self.source.sheet}:{self.source.excel_row}":
            raise ValueError("row_id must match source location")
        return self


class Scale(StrictModel):
    numerator: Literal[1] = 1
    denominator: ScaleDenominatorString
    label: ScaleLabelString

    @field_validator("numerator", mode="before")
    @classmethod
    def numerator_is_strict_one(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("numerator must be integer 1")
        return value

    @model_validator(mode="after")
    def label_matches_denominator(self) -> "Scale":
        if self.label != f"1:{self.denominator}":
            raise ValueError("label must match denominator")
        return self


class HeaterRow(StrictModel):
    schema_version: Literal[1] = 1
    row_id: RowId
    source: SourceLocation
    raw: RawHeaterFields
    values: HeaterFields

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_strict_one(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value

    @model_validator(mode="after")
    def row_id_matches_source(self) -> "HeaterRow":
        if self.row_id != f"{self.source.sheet}:{self.source.excel_row}":
            raise ValueError("row_id must match source location")
        return self


class Issue(StrictModel):
    issue_id: UUID
    row_id: RowId | None = None
    sheet: str | None = None
    excel_row: StrictExcelRow | None = None
    code: str | None = None
    field: str | None = None
    raw_value: Any | None = None
    error_code: ErrorCode
    severity: Severity
    message: str = Field(min_length=1)
    suggested_fix: str = Field(min_length=1)
    scope: IssueScope
    skippable: StrictBool

    @model_validator(mode="after")
    def validate_location_and_skip(self) -> "Issue":
        location = (self.row_id, self.sheet, self.excel_row)
        if self.scope == IssueScope.ROW and any(value is None for value in location):
            raise ValueError("row issues require row_id, sheet, and excel_row")
        if any(value is not None for value in location):
            if any(value is None for value in location):
                raise ValueError("issue row location must be complete")
            if self.row_id != f"{self.sheet}:{self.excel_row}":
                raise ValueError("issue row_id must match sheet and excel_row")
        if self.scope != IssueScope.ROW and self.skippable:
            raise ValueError("only row issues may be skippable")
        return self


class Bounds(StrictModel):
    left: SignedDecimalString
    bottom: SignedDecimalString
    right: SignedDecimalString
    top: SignedDecimalString


class ScaleProposal(StrictModel):
    proposal_id: UUID
    row_id: RowId
    original: Scale
    proposed: Scale
    reason: str = Field(min_length=1)
    measured_bounds_paper_mm: Bounds
    available_bounds_paper_mm: Bounds
    revision_hash: Sha256
    template_hash: Sha256


class Decision(StrictModel):
    decision_id: UUID
    actor_id: str = Field(min_length=1)
    decided_at: datetime
    kind: DecisionKind
    base_revision_hash: Sha256
    issue_ids: list[UUID] = Field(default_factory=list)
    proposal_ids: list[UUID] = Field(default_factory=list)
    row_ids: list[RowId] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    confirmation_receipt_id: str = Field(min_length=1)


class RevisionContent(StrictModel):
    revision_id: UUID
    parent_revision_id: UUID | None
    source_sha256: Sha256
    template_version: str = Field(min_length=1)
    template_hash: Sha256
    font_manifest_hash: Sha256
    output_profile: str = Field(min_length=1)
    rows: list[HeaterRow] = Field(min_length=1)
    final_scales: dict[RowId, Scale]
    issues: list[Issue]
    proposals: list[ScaleProposal]
    decisions: list[Decision]
    skipped_row_ids: list[RowId]
    expected_row_ids: list[RowId] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_row_sets(self) -> "RevisionContent":
        row_ids = [row.row_id for row in self.rows]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("revision rows must have unique row_id values")
        if len(self.skipped_row_ids) != len(set(self.skipped_row_ids)):
            raise ValueError("skipped_row_ids must be unique")
        if len(self.expected_row_ids) != len(set(self.expected_row_ids)):
            raise ValueError("expected_row_ids must be unique")
        if set(self.final_scales) != set(row_ids):
            raise ValueError("final_scales must cover every revision row exactly")
        if set(self.skipped_row_ids) & set(self.expected_row_ids):
            raise ValueError("skipped and expected row sets must be disjoint")
        if set(self.skipped_row_ids) | set(self.expected_row_ids) != set(row_ids):
            raise ValueError("skipped and expected row sets must partition revision rows")
        derived_expected = [
            row_id for row_id in row_ids if row_id not in set(self.skipped_row_ids)
        ]
        if self.expected_row_ids != derived_expected:
            raise ValueError(
                "expected_row_ids must preserve revision row order after skipped rows"
            )
        return self


class SkippedRowHashBinding(StrictModel):
    row_id: RowId
    decision_id: UUID
    issue_ids: list[UUID]
    reason: str = Field(min_length=1)
    confirmation_receipt_id: str = Field(min_length=1)


class RevisionHashPayload(StrictModel):
    schema_version: Literal[1] = 1
    source_sha256: Sha256
    rows: list[HeaterRow] = Field(min_length=1)
    template_version: str = Field(min_length=1)
    template_hash: Sha256
    font_manifest_hash: Sha256
    output_profile: str = Field(min_length=1)
    final_scales: dict[RowId, Scale]
    skipped_rows: list[SkippedRowHashBinding]

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_strict_one(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value


class Revision(RevisionContent):
    revision_hash: Sha256

    @model_validator(mode="after")
    def revision_hash_matches_content(self) -> "Revision":
        expected = compute_revision_hash(self)
        if self.revision_hash != expected:
            raise ValueError("revision_hash does not match the canonical revision payload")
        return self

    @classmethod
    def create(cls, **content: Any) -> "Revision":
        validated = RevisionContent.model_validate(content)
        payload = validated.model_dump(mode="json")
        payload["revision_hash"] = compute_revision_hash(validated)
        return cls.model_validate(payload)


def _skip_bindings(content: RevisionContent) -> list[SkippedRowHashBinding]:
    skip_decisions = [
        decision for decision in content.decisions if decision.kind == DecisionKind.SKIP
    ]
    decision_rows = {
        row_id for decision in skip_decisions for row_id in decision.row_ids
    }
    if decision_rows != set(content.skipped_row_ids):
        raise ValueError(
            "skip decisions must cover skipped_row_ids exactly and no other rows"
        )
    bindings: list[SkippedRowHashBinding] = []
    for row_id in content.skipped_row_ids:
        matches = [
            decision for decision in skip_decisions if row_id in decision.row_ids
        ]
        if len(matches) != 1:
            raise ValueError("each skipped row requires exactly one skip decision")
        decision = matches[0]
        skippable_row_issue_ids = {
            issue.issue_id
            for issue in content.issues
            if issue.row_id == row_id
            and issue.scope == IssueScope.ROW
            and issue.skippable
        }
        skippable_row_error_ids = {
            issue.issue_id
            for issue in content.issues
            if issue.row_id == row_id
            and issue.scope == IssueScope.ROW
            and issue.skippable
            and issue.severity == Severity.ERROR
        }
        if not skippable_row_error_ids.issubset(set(decision.issue_ids)):
            raise ValueError(
                "skip decision must cover every skippable row error for its row"
            )
        if not set(decision.issue_ids).issubset(skippable_row_issue_ids):
            raise ValueError(
                "skip decision may reference only skippable row issues from its row"
            )
        bindings.append(
            SkippedRowHashBinding(
                row_id=row_id,
                decision_id=decision.decision_id,
                issue_ids=sorted(decision.issue_ids, key=str),
                reason=decision.reason,
                confirmation_receipt_id=decision.confirmation_receipt_id,
            )
        )
    return bindings


def revision_hash_payload(
    value: RevisionContent | Mapping[str, Any],
) -> RevisionHashPayload:
    if isinstance(value, RevisionContent):
        content = value
    else:
        data = dict(value)
        data.pop("revision_hash", None)
        content = RevisionContent.model_validate(data)
    return RevisionHashPayload(
        source_sha256=content.source_sha256,
        rows=content.rows,
        template_version=content.template_version,
        template_hash=content.template_hash,
        font_manifest_hash=content.font_manifest_hash,
        output_profile=content.output_profile,
        final_scales=content.final_scales,
        skipped_rows=_skip_bindings(content),
    )


def compute_revision_hash(value: RevisionContent | Mapping[str, Any]) -> str:
    payload = revision_hash_payload(value)
    return canonical_sha256(payload)


def validate_revision_hash(value: Revision | Mapping[str, Any]) -> Revision:
    payload = value.model_dump(mode="json") if isinstance(value, Revision) else value
    return Revision.model_validate(payload)


class Point(StrictModel):
    x: SignedDecimalString
    y: SignedDecimalString


class RectangleGeometry(StrictModel):
    origin: Point
    width_mm: PositiveDecimalString
    length_mm: PositiveDecimalString


class LeadSegment(StrictModel):
    start: Point
    end: Point


class DimensionDefinition(StrictModel):
    measurement: Literal["width", "length"]
    value_mm: PositiveDecimalString


class Geometry(StrictModel):
    rectangle: RectangleGeometry
    lead_segments: list[LeadSegment] = Field(min_length=2, max_length=2)
    dimension_definitions: list[DimensionDefinition] = Field(
        min_length=2,
        max_length=2,
    )


class Placement(StrictModel):
    model_origin_mm: Point
    tile_bounds_mm: Bounds
    paper_bounds_mm: Bounds
    layout_name: str = Field(min_length=1)


class CheckResult(StrictModel):
    passed: StrictBool
    details: list[str] = Field(default_factory=list)


class DrawingChecks(StrictModel):
    bounds: CheckResult
    collisions: CheckResult
    glyph_coverage: CheckResult


class DrawingPage(StrictModel):
    schema_version: Literal[1] = 1
    row_id: RowId
    code: str = Field(min_length=1)
    revision_hash: Sha256
    template_hash: Sha256
    scale: Scale
    geometry_mm: Geometry
    fields: HeaterFields
    fixed_text_version: str = Field(min_length=1)
    placement: Placement
    checks: DrawingChecks

    @field_validator("schema_version", mode="before")
    @classmethod
    def schema_version_is_strict_one(cls, value: Any) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema_version must be integer 1")
        return value


class Artifact(StrictModel):
    artifact_id: UUID
    run_id: UUID
    revision_hash: Sha256
    relative_path: SafeRelativePath
    media_type: str = Field(min_length=1)
    bytes: StrictNonNegativeInt
    sha256: Sha256
    row_ids: list[RowId]
    page_count: StrictPositiveInt | None = None
    page_index: StrictPositiveInt | None = None
    kind: ArtifactKind


class ErrorDetail(StrictModel):
    code: ErrorCode
    message: str = Field(min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(min_length=1)
    current_revision_hash: Sha256 | None = None


class ErrorResponse(StrictModel):
    error: ErrorDetail


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "heater-row.schema.json": HeaterRow,
    "revision.schema.json": Revision,
    "drawing-page.schema.json": DrawingPage,
    "artifact.schema.json": Artifact,
    "error.schema.json": ErrorResponse,
}


def canonical_json_bytes(value: Any) -> bytes:
    """Serialize JSON-compatible contract data deterministically."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def validate_contract_semantics(
    schema_name: str,
    payload: Mapping[str, Any],
) -> BaseModel:
    """Mandatory semantic validation after Draft 2020-12 structure checks."""

    try:
        model = SCHEMA_MODELS[schema_name]
    except KeyError as exc:
        raise ValueError(f"unknown contract schema: {schema_name}") from exc
    return model.model_validate(payload)


def _apply_semantic_annotations(
    name: str,
    schema: dict[str, Any],
) -> None:
    schema["x-semantic-validator"] = (
        "heater_drawing.domain.models.validate_contract_semantics"
    )
    schema["x-validation-order"] = [
        "draft-2020-12-structure",
        "shared-python-semantics",
    ]
    definitions = schema.get("$defs", {})
    for definition_name in ("HeaterRow", "Scale", "Issue", "Revision"):
        if definition_name in definitions:
            definitions[definition_name]["x-semantic-validator"] = (
                "heater_drawing.domain.models.validate_contract_semantics"
            )

    issue = definitions.get("Issue")
    if issue is not None:
        issue.setdefault("allOf", []).extend(
            [
                {
                    "if": {
                        "properties": {"scope": {"const": "row"}},
                        "required": ["scope"],
                    },
                    "then": {
                        "required": ["row_id", "sheet", "excel_row"],
                        "properties": {
                            "row_id": {
                                "type": "string",
                                "pattern": ROW_ID_PATTERN,
                            },
                            "sheet": {"type": "string", "minLength": 1},
                            "excel_row": {"type": "integer", "minimum": 2},
                        },
                    },
                    "else": {
                        "properties": {"skippable": {"const": False}},
                    },
                },
                {
                    "if": {
                        "anyOf": [
                            {
                                "required": ["row_id"],
                                "properties": {
                                    "row_id": {"not": {"type": "null"}}
                                },
                            },
                            {
                                "required": ["sheet"],
                                "properties": {
                                    "sheet": {"not": {"type": "null"}}
                                },
                            },
                            {
                                "required": ["excel_row"],
                                "properties": {
                                    "excel_row": {"not": {"type": "null"}}
                                },
                            },
                        ]
                    },
                    "then": {
                        "required": ["row_id", "sheet", "excel_row"],
                        "properties": {
                            "row_id": {
                                "type": "string",
                                "pattern": ROW_ID_PATTERN,
                            },
                            "sheet": {"type": "string", "minLength": 1},
                            "excel_row": {"type": "integer", "minimum": 2},
                        },
                    },
                },
            ]
        )


def schema_snapshot(name: str) -> dict[str, Any]:
    model = SCHEMA_MODELS[name]
    schema = model.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"https://dsh.local/heater-drawing/v1/{name}"
    _apply_semantic_annotations(name, schema)
    return schema
