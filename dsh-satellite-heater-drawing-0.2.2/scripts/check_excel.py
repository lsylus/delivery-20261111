#!/usr/bin/env python3
"""Parse and validate one heater workbook, emitting a complete JSON report."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from heater_drawing.domain.errors import make_issue
from heater_drawing.domain.models import (
    ErrorCode,
    Issue,
    IssueScope,
    Severity,
)
from heater_drawing.excel import WorkbookLimits, parse_workbook, validate_rows
from heater_drawing.excel.actual_workbook import write_actual_workbook


def _flatten(row: object) -> dict[str, object]:
    values = row.values.model_dump(mode="json")
    return {"excel_row": row.source.excel_row, **values}


def _write_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _system_issue(
    error_code: ErrorCode,
    message: str,
    suggested_fix: str,
    raw_value: object,
) -> Issue:
    return make_issue(
        error_code=error_code,
        severity=Severity.ERROR,
        message=message,
        suggested_fix=suggested_fix,
        scope=IssueScope.SYSTEM,
        field="limits" if error_code == ErrorCode.INVALID_REQUEST else None,
        raw_value=raw_value,
        skippable=False,
    )


def _configured_limits(args: argparse.Namespace) -> WorkbookLimits:
    integer_names = (
        "max_file_bytes",
        "max_business_rows",
        "max_populated_rows_per_sheet",
        "max_columns",
        "max_zip_entries",
        "max_uncompressed_bytes",
        "max_text_characters",
    )
    values = {name: int(getattr(args, name)) for name in integer_names}
    values["max_compression_ratio"] = float(args.max_compression_ratio)
    return WorkbookLimits(**values)


def _raw_limits(args: argparse.Namespace) -> dict[str, str]:
    return {
        name: str(getattr(args, name))
        for name in (
            "max_file_bytes",
            "max_business_rows",
            "max_populated_rows_per_sheet",
            "max_columns",
            "max_zip_entries",
            "max_uncompressed_bytes",
            "max_compression_ratio",
            "max_text_characters",
        )
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--actual-output", type=Path)
    parser.add_argument("--max-file-bytes", default=str(10 * 1024 * 1024))
    parser.add_argument("--max-business-rows", default="500")
    parser.add_argument("--max-populated-rows-per-sheet", default="501")
    parser.add_argument("--max-columns", default="64")
    parser.add_argument("--max-zip-entries", default="2000")
    parser.add_argument(
        "--max-uncompressed-bytes", default=str(100 * 1024 * 1024)
    )
    parser.add_argument("--max-compression-ratio", default="1000.0")
    parser.add_argument("--max-text-characters", default="256")
    args = parser.parse_args()

    try:
        limits = _configured_limits(args)
    except (OverflowError, TypeError, ValueError) as exc:
        issue = _system_issue(
            ErrorCode.INVALID_REQUEST,
            f"工作簿限制配置无效: {exc}",
            "使用正有限数配置压缩比，并为其他限制填写正整数；文字上限不超过 256",
            _raw_limits(args),
        )
        payload = {
            "schema_version": 1,
            "status": "invalid",
            "source": args.input.name,
            "source_sha256": None,
            "sheet": "Sheet1",
            "record_count": 0,
            "normalized_row_count": 0,
            "rows": [],
            "source_rows": [],
            "issues": [issue.model_dump(mode="json")],
            "limits": _raw_limits(args),
            "outputs": [],
        }
        _write_payload(args.output, payload)
        return 1

    parsed = parse_workbook(args.input, limits)
    validated = validate_rows(parsed.rows, limits=limits)
    issues = [*parsed.issues, *validated.issues]
    issues.sort(
        key=lambda issue: (
            issue.excel_row if issue.excel_row is not None else 0,
            issue.field or "",
            issue.error_code.value,
            str(issue.issue_id),
        )
    )
    valid_by_id = {row.row_id: row for row in validated.rows}
    issue_ids_by_row: dict[str, list[str]] = {}
    for issue in issues:
        if issue.row_id is not None:
            issue_ids_by_row.setdefault(issue.row_id, []).append(str(issue.issue_id))
    payload = {
        "schema_version": 1,
        "status": "invalid"
        if any(issue.severity == Severity.ERROR for issue in issues)
        else "valid",
        "source": args.input.name,
        "source_sha256": parsed.source_sha256,
        "sheet": parsed.sheet,
        "record_count": len(parsed.rows),
        "normalized_row_count": len(validated.rows),
        "rows": [_flatten(row) for row in validated.rows],
        "source_rows": [
            {
                **row.model_dump(mode="json"),
                "values": valid_by_id[row.row_id].values.model_dump(mode="json")
                if row.row_id in valid_by_id
                else None,
                "issue_ids": issue_ids_by_row.get(row.row_id, []),
            }
            for row in parsed.rows
        ],
        "issues": [issue.model_dump(mode="json") for issue in issues],
        "limits": asdict(limits),
        "outputs": [],
    }
    if args.actual_output is not None and payload["status"] == "valid":
        try:
            write_actual_workbook(args.actual_output, validated.rows)
        except Exception as exc:
            issue = _system_issue(
                ErrorCode.INTERNAL_ERROR,
                f"无法写出实际值工作簿: {type(exc).__name__}",
                "保留输入和诊断报告，并检查服务日志后重试",
                str(exc),
            )
            payload["status"] = "invalid"
            payload["issues"].append(issue.model_dump(mode="json"))
        else:
            payload["outputs"].append(
                {"kind": "excel_actual", "path": str(args.actual_output)}
            )
    _write_payload(args.output, payload)
    return 0 if payload["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
