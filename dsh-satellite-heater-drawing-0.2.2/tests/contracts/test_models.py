from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
import pytest
from pydantic import ValidationError

from heater_drawing.config import ResourceConfig, ServiceConfig
from heater_drawing.domain.models import (
    Artifact,
    ErrorCode,
    ErrorResponse,
    HeaterRow,
    Issue,
    Revision,
    SCHEMA_MODELS,
    Scale,
    canonical_json_bytes,
    canonical_sha256,
    compute_revision_hash,
    revision_hash_payload,
    schema_snapshot,
    validate_contract_semantics,
    validate_revision_hash,
)

ROOT = Path(__file__).resolve().parents[2]


def row_payload(excel_row: int = 2) -> dict[str, object]:
    values = json.loads(
        (ROOT / "fixtures/case/expected.json").read_text(encoding="utf-8")
    )["rows"][0]
    values = {key: value for key, value in values.items() if key != "excel_row"}
    if excel_row != 2:
        values["code"] = f"ROW-{excel_row}"
    return {
        "schema_version": 1,
        "row_id": f"Sheet1:{excel_row}",
        "source": {"sheet": "Sheet1", "excel_row": excel_row},
        "raw": deepcopy(values),
        "values": deepcopy(values),
    }


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(
        schema_snapshot(name),
        format_checker=FormatChecker(),
    )


def revision_content() -> dict[str, object]:
    row2 = row_payload(2)
    row3 = row_payload(3)
    decision_id = "55555555-5555-4555-8555-555555555555"
    return {
        "revision_id": "11111111-1111-4111-8111-111111111111",
        "parent_revision_id": None,
        "source_sha256": "1" * 64,
        "template_version": "heater-a4-v1",
        "template_hash": "2" * 64,
        "font_manifest_hash": "3" * 64,
        "output_profile": "dxf-pdf-v1",
        "rows": [row2, row3],
        "final_scales": {
            "Sheet1:2": {"numerator": 1, "denominator": "1", "label": "1:1"},
            "Sheet1:3": {"numerator": 1, "denominator": "2", "label": "1:2"},
        },
        "issues": [
            {
                "issue_id": "44444444-4444-4444-8444-444444444444",
                "row_id": "Sheet1:3",
                "sheet": "Sheet1",
                "excel_row": 3,
                "code": "ROW-3",
                "field": "width_mm",
                "error_code": "INVALID_FIELD",
                "severity": "error",
                "message": "invalid width",
                "suggested_fix": "correct or explicitly skip the row",
                "scope": "row",
                "skippable": True,
            }
        ],
        "proposals": [],
        "decisions": [
            {
                "decision_id": decision_id,
                "actor_id": "engineer-1",
                "decided_at": "2026-11-07T08:00:00Z",
                "kind": "skip",
                "base_revision_hash": "0" * 64,
                "issue_ids": ["44444444-4444-4444-8444-444444444444"],
                "proposal_ids": [],
                "row_ids": ["Sheet1:3"],
                "reason": "fixture skip reason",
                "confirmation_receipt_id": "receipt-1",
            }
        ],
        "skipped_row_ids": ["Sheet1:3"],
        "expected_row_ids": ["Sheet1:2"],
    }


def test_heater_row_accepts_exact_17_fields_and_known_rows() -> None:
    for excel_row in (2, 9, 10, 19, 20, 99, 100, 1048576):
        row = HeaterRow.model_validate(row_payload(excel_row))
        assert row.row_id == f"Sheet1:{excel_row}"
        assert len(type(row.values).model_fields) == 17


@pytest.mark.parametrize(
    "value",
    [True, 1, "NaN", "Inf", "-1", "0", "1e2", "01", "1٢", "1\n"],
)
def test_positive_decimal_rejects_non_contract_values(value: object) -> None:
    payload = row_payload()
    payload["values"]["width_mm"] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        HeaterRow.model_validate(payload)
    assert not validator("heater-row.schema.json").is_valid(payload)


@pytest.mark.parametrize("value", ["0.001", "1", "1.5", "200"])
def test_positive_decimal_keeps_ordinary_positive_fractions(value: str) -> None:
    payload = row_payload()
    payload["values"]["width_mm"] = value  # type: ignore[index]
    assert HeaterRow.model_validate(payload).values.width_mm == value
    assert validator("heater-row.schema.json").is_valid(payload)


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("1:1", True),
        ("1:1.5", True),
        ("1:2", True),
        ("1:0.5", False),
        ("1:0", False),
        ("1:-1", False),
        ("1:NaN", False),
        ("1:Inf", False),
    ],
)
def test_requested_scale_denominator_is_at_least_one(
    value: str,
    accepted: bool,
) -> None:
    payload = row_payload()
    payload["values"]["requested_scale"] = value  # type: ignore[index]
    assert validator("heater-row.schema.json").is_valid(payload) is accepted
    if accepted:
        HeaterRow.model_validate(payload)
    else:
        with pytest.raises(ValidationError):
            HeaterRow.model_validate(payload)


@pytest.mark.parametrize("value", [True, 2, "1", None])
def test_schema_version_and_scale_numerator_are_strict(value: object) -> None:
    payload = row_payload()
    payload["schema_version"] = value
    with pytest.raises(ValidationError):
        HeaterRow.model_validate(payload)
    assert not validator("heater-row.schema.json").is_valid(payload)

    scale = {"numerator": value, "denominator": "2", "label": "1:2"}
    with pytest.raises(ValidationError):
        Scale.model_validate(scale)
    scale_schema = schema_snapshot("revision.schema.json")["$defs"]["Scale"]
    assert not Draft202012Validator(scale_schema).is_valid(scale)


def test_service_config_version_is_fixed(tmp_path: Path) -> None:
    (tmp_path / "schemas").mkdir()
    resource = ResourceConfig.from_root(tmp_path)
    assert ServiceConfig(resource=resource).schema_version == 1
    for value in (True, 2, "1"):
        with pytest.raises(ValidationError):
            ServiceConfig(schema_version=value, resource=resource)


def test_structural_and_semantic_validation_boundaries_are_explicit() -> None:
    row = row_payload()
    row["row_id"] = "Sheet1:3"
    assert validator("heater-row.schema.json").is_valid(row)
    with pytest.raises(ValidationError):
        validate_contract_semantics("heater-row.schema.json", row)

    scale = {"numerator": 1, "denominator": "2", "label": "1:5"}
    revision_schema = schema_snapshot("revision.schema.json")
    assert Draft202012Validator(revision_schema["$defs"]["Scale"]).is_valid(scale)
    with pytest.raises(ValidationError):
        Scale.model_validate(scale)


def test_unknown_fields_and_invalid_uuid_are_rejected_across_layers() -> None:
    row = row_payload()
    row["tool_path"] = "/tmp/unsafe"
    with pytest.raises(ValidationError):
        HeaterRow.model_validate(row)
    assert not validator("heater-row.schema.json").is_valid(row)

    issue = {
        "issue_id": "not-a-uuid",
        "error_code": "INVALID_FIELD",
        "severity": "error",
        "message": "bad",
        "suggested_fix": "fix",
        "scope": "system",
        "skippable": False,
    }
    with pytest.raises(ValidationError):
        Issue.model_validate(issue)
    revision_schema = schema_snapshot("revision.schema.json")
    issue_schema = {
        "$schema": revision_schema["$schema"],
        "$defs": revision_schema["$defs"],
        **revision_schema["$defs"]["Issue"],
    }
    assert not Draft202012Validator(
        issue_schema,
        format_checker=FormatChecker(),
    ).is_valid(issue)


def test_issue_structure_skip_and_location_are_consistent() -> None:
    base = {
        "issue_id": "44444444-4444-4444-8444-444444444444",
        "error_code": "INVALID_FIELD",
        "severity": "error",
        "message": "bad",
        "suggested_fix": "fix",
        "scope": "row",
        "skippable": True,
    }
    revision_schema = schema_snapshot("revision.schema.json")
    issue_schema = {
        "$schema": revision_schema["$schema"],
        "$defs": revision_schema["$defs"],
        **revision_schema["$defs"]["Issue"],
    }
    assert not Draft202012Validator(issue_schema).is_valid(base)
    with pytest.raises(ValidationError):
        Issue.model_validate(base)

    mismatched = {
        **base,
        "row_id": "Sheet1:2",
        "sheet": "Sheet1",
        "excel_row": 3,
    }
    assert Draft202012Validator(issue_schema).is_valid(mismatched)
    with pytest.raises(ValidationError):
        Issue.model_validate(mismatched)

    system_skip = {
        **base,
        "scope": "system",
        "skippable": True,
        "row_id": "Sheet1:2",
        "sheet": "Sheet1",
        "excel_row": 2,
    }
    assert not Draft202012Validator(issue_schema).is_valid(system_skip)
    with pytest.raises(ValidationError):
        Issue.model_validate(system_skip)


@pytest.mark.parametrize("scope", ["system", "workbook"])
def test_non_row_issue_default_json_roundtrips_through_public_contract(
    scope: str,
) -> None:
    payload = {
        "issue_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "error_code": "CAPABILITY_UNAVAILABLE",
        "severity": "error",
        "message": "capability unavailable",
        "suggested_fix": "configure the required capability",
        "scope": scope,
        "skippable": False,
    }
    serialized = Issue.model_validate(payload).model_dump(mode="json")
    assert serialized["row_id"] is None
    assert serialized["sheet"] is None
    assert serialized["excel_row"] is None
    revision_schema = schema_snapshot("revision.schema.json")
    issue_schema = {
        "$schema": revision_schema["$schema"],
        "$defs": revision_schema["$defs"],
        **revision_schema["$defs"]["Issue"],
    }
    Draft202012Validator(issue_schema).validate(serialized)

    invalid_partial = {**serialized, "sheet": "Sheet1"}
    assert not Draft202012Validator(issue_schema).is_valid(invalid_partial)
    with pytest.raises(ValidationError):
        Issue.model_validate(invalid_partial)


def test_revision_default_json_roundtrips_schema_and_shared_semantics() -> None:
    content = revision_content()
    content["issues"].append(  # type: ignore[union-attr]
        {
            "issue_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            "error_code": "CAPABILITY_UNAVAILABLE",
            "severity": "error",
            "message": "capability unavailable",
            "suggested_fix": "configure capability",
            "scope": "system",
            "skippable": False,
        }
    )
    content["issues"].append(  # type: ignore[union-attr]
        {
            "issue_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
            "error_code": "INVALID_REQUEST",
            "severity": "error",
            "message": "workbook issue",
            "suggested_fix": "correct workbook",
            "scope": "workbook",
            "skippable": False,
        }
    )
    serialized = Revision.create(**content).model_dump(mode="json")
    validator("revision.schema.json").validate(serialized)
    validated = validate_contract_semantics("revision.schema.json", serialized)
    assert isinstance(validated, Revision)


def test_safe_artifact_path_is_enforced_by_model_and_schema() -> None:
    payload = {
        "artifact_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "run_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "revision_hash": "0" * 64,
        "relative_path": "../escape.pdf",
        "media_type": "application/pdf",
        "bytes": 1,
        "sha256": "1" * 64,
        "row_ids": [],
        "page_count": 1,
        "kind": "pdf_single",
    }
    with pytest.raises(ValidationError):
        Artifact.model_validate(payload)
    assert not validator("artifact.schema.json").is_valid(payload)


def test_error_code_is_one_shared_closed_enum() -> None:
    error_schema = schema_snapshot("error.schema.json")
    schema_values = set(error_schema["$defs"]["ErrorCode"]["enum"])
    assert schema_values == {item.value for item in ErrorCode}
    for code in ErrorCode:
        issue = {
            "issue_id": "44444444-4444-4444-8444-444444444444",
            "error_code": code.value,
            "severity": "warning",
            "message": "message",
            "suggested_fix": "fix",
            "scope": "system",
            "skippable": False,
        }
        assert Issue.model_validate(issue).error_code is code
        response = {
            "error": {
                "code": code.value,
                "message": "message",
                "request_id": "request-1",
            }
        }
        assert ErrorResponse.model_validate(response).error.code is code
        assert validator("error.schema.json").is_valid(response)

    for unknown in ("TOTALLY_UNREGISTERED_ERROR", "worker_interrupted", "WORKER-INTERRUPTED"):
        with pytest.raises(ValidationError):
            ErrorResponse.model_validate(
                {"error": {"code": unknown, "message": "bad", "request_id": "r"}}
            )


def test_canonical_json_is_stable_and_rejects_nan() -> None:
    left = {"名字": "加热器", "b": 2, "a": 1}
    right = {"a": 1, "b": 2, "名字": "加热器"}
    assert canonical_json_bytes(left) == b'{"a":1,"b":2,"\xe5\x90\x8d\xe5\xad\x97":"\xe5\x8a\xa0\xe7\x83\xad\xe5\x99\xa8"}'
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert canonical_sha256(left) == canonical_sha256(right)
    with pytest.raises(ValueError):
        canonical_json_bytes({"bad": float("nan")})


def test_revision_hash_has_a_dedicated_payload_and_validation_entry() -> None:
    content = revision_content()
    revision = Revision.create(**content)
    payload = revision_hash_payload(revision).model_dump(mode="json")
    independently_serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    expected = hashlib.sha256(independently_serialized).hexdigest()
    assert expected == "dbe524a38d4405d47335820a14b0758e2556c2ac53c2cb7e8368f2a5484c5807"
    assert revision.revision_hash == expected
    assert compute_revision_hash(dict(reversed(list(content.items())))) == expected
    assert validate_revision_hash(revision).revision_hash == expected

    invalid = revision.model_dump(mode="json")
    invalid["revision_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        validate_revision_hash(invalid)


def test_revision_instance_mutations_are_revalidated_and_rejected() -> None:
    revision = Revision.create(**revision_content())
    mapping = revision.model_dump(mode="json")
    assert validate_revision_hash(mapping).revision_hash == revision.revision_hash

    revision.final_scales["Sheet1:2"] = Scale(
        numerator=1,
        denominator="2",
        label="1:2",
    )
    with pytest.raises(ValidationError):
        validate_revision_hash(revision)

    reordered = Revision.create(**revision_content())
    reordered.rows.reverse()
    with pytest.raises(ValidationError):
        validate_revision_hash(reordered)

    changed_skip = Revision.create(**revision_content())
    changed_skip.decisions[0].row_ids.clear()
    with pytest.raises((ValidationError, ValueError)):
        validate_revision_hash(changed_skip)


def test_expected_row_ids_are_derived_in_original_row_order() -> None:
    content = revision_content()
    content["decisions"] = []
    content["skipped_row_ids"] = []
    content["expected_row_ids"] = ["Sheet1:2", "Sheet1:3"]
    valid = Revision.create(**content)
    assert valid.expected_row_ids == ["Sheet1:2", "Sheet1:3"]

    content["expected_row_ids"] = ["Sheet1:3", "Sheet1:2"]
    with pytest.raises(ValidationError):
        Revision.create(**content)


@pytest.mark.parametrize(
    "mutation",
    [
        "source_sha256",
        "template_version",
        "template_hash",
        "font_manifest_hash",
        "output_profile",
        "final_scale",
        "skipped_row",
        "skip_reason",
    ],
)
def test_revision_hash_changes_for_every_c01_binding(mutation: str) -> None:
    original = revision_content()
    changed = deepcopy(original)
    if mutation == "source_sha256":
        changed["source_sha256"] = "9" * 64
    elif mutation == "template_version":
        changed["template_version"] = "heater-a4-v2"
    elif mutation == "template_hash":
        changed["template_hash"] = "8" * 64
    elif mutation == "font_manifest_hash":
        changed["font_manifest_hash"] = "7" * 64
    elif mutation == "output_profile":
        changed["output_profile"] = "changed-profile"
    elif mutation == "final_scale":
        changed["final_scales"]["Sheet1:2"] = {  # type: ignore[index]
            "numerator": 1,
            "denominator": "5",
            "label": "1:5",
        }
    elif mutation == "skipped_row":
        changed["skipped_row_ids"] = ["Sheet1:2"]
        changed["expected_row_ids"] = ["Sheet1:3"]
        changed["decisions"][0]["row_ids"] = ["Sheet1:2"]  # type: ignore[index]
        changed["decisions"][0]["issue_ids"] = []  # type: ignore[index]
    elif mutation == "skip_reason":
        changed["decisions"][0]["reason"] = "changed skip reason"  # type: ignore[index]
    assert compute_revision_hash(changed) != compute_revision_hash(original)


def test_revision_hash_binds_each_of_the_17_raw_and_normalized_fields() -> None:
    original = revision_content()
    original_hash = compute_revision_hash(original)
    fields = original["rows"][0]["values"]  # type: ignore[index]
    assert len(fields) == 17
    for section in ("raw", "values"):
        for field, value in fields.items():
            changed = deepcopy(original)
            if field == "lead_side":
                replacement = "long"
            elif field == "requested_scale":
                replacement = "1:5"
            elif field in {
                "width_mm",
                "length_mm",
                "resistance_ohm",
                "tolerance_ohm",
            }:
                replacement = "99.5"
            else:
                replacement = f"{value}-changed"
            changed["rows"][0][section][field] = replacement  # type: ignore[index]
            assert compute_revision_hash(changed) != original_hash, (
                section,
                field,
            )


def test_revision_hash_rejects_missing_skip_binding_and_invalid_number() -> None:
    missing = revision_content()
    missing["decisions"] = []
    with pytest.raises(ValueError):
        Revision.create(**missing)

    invalid = revision_content()
    invalid["rows"][0]["values"]["width_mm"] = "NaN"  # type: ignore[index]
    with pytest.raises(ValidationError):
        Revision.create(**invalid)


def test_json_schema_snapshots_match_models_and_declare_semantics() -> None:
    for name in SCHEMA_MODELS:
        actual = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
        assert actual == schema_snapshot(name)
        assert actual["x-semantic-validator"].endswith(
            "validate_contract_semantics"
        )
