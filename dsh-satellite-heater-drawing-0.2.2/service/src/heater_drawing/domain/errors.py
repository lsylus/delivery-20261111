"""Issue construction shared by import and validation layers."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid5

from heater_drawing.domain.models import (
    ErrorCode,
    Issue,
    IssueScope,
    Severity,
)


ISSUE_NAMESPACE = UUID("929ac50f-e0ad-4b2a-a7c6-a08b7548bedc")


def make_issue(
    *,
    error_code: ErrorCode,
    severity: Severity,
    message: str,
    suggested_fix: str,
    scope: IssueScope,
    row_id: str | None = None,
    sheet: str | None = None,
    excel_row: int | None = None,
    code: str | None = None,
    field: str | None = None,
    raw_value: Any | None = None,
    skippable: bool = False,
) -> Issue:
    """Build a deterministic issue without introducing another error shape."""

    identity = json.dumps(
        {
            "error_code": error_code.value,
            "scope": scope.value,
            "row_id": row_id,
            "sheet": sheet,
            "excel_row": excel_row,
            "code": code,
            "field": field,
            "raw_value": raw_value,
            "message": message,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return Issue(
        issue_id=uuid5(ISSUE_NAMESPACE, identity),
        row_id=row_id,
        sheet=sheet,
        excel_row=excel_row,
        code=code,
        field=field,
        raw_value=raw_value,
        error_code=error_code,
        severity=severity,
        message=message,
        suggested_fix=suggested_fix,
        scope=scope,
        skippable=skippable,
    )
