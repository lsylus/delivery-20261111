"""Non-drawing validation for imported heater rows."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from datetime import date, datetime, time
import math
from pathlib import PureWindowsPath
import re
from typing import Any, Iterable, Mapping
import unicodedata

from heater_drawing.domain.errors import make_issue
from heater_drawing.domain.models import (
    ErrorCode,
    HeaterFields,
    HeaterRow,
    ImportedHeaterRow,
    Issue,
    IssueScope,
    LeadSide,
    Severity,
)
from heater_drawing.excel.headers import FIELD_ORDER
from heater_drawing.excel.reader import WorkbookLimits
from heater_drawing.excel.numeric import UnsupportedExcelNumeric, exact_excel_numeric


NUMERIC_FIELDS = (
    "width_mm",
    "length_mm",
    "resistance_ohm",
    "tolerance_ohm",
)
POSITIVE_FIELDS = {"width_mm", "length_mm", "resistance_ohm"}
TEXT_FIELDS = (
    "name",
    "quantity_text",
    "organization",
    "model",
    "designer",
    "checker",
    "reviewer",
    "standards_reviewer",
    "approver",
    "stage",
)
ASCII_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", re.ASCII)
SCALE = re.compile(r"1:((?:0|[1-9][0-9]*)(?:\.[0-9]+)?)", re.ASCII)
FORBIDDEN_FILENAME = set('<>:"/\\|?*')


@dataclass(frozen=True, slots=True)
class ValidationResult:
    source_rows: tuple[ImportedHeaterRow, ...]
    rows: tuple[HeaterRow, ...]
    issues: tuple[Issue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)


def _limits(value: WorkbookLimits | Mapping[str, Any] | None) -> WorkbookLimits:
    if value is None:
        return WorkbookLimits()
    if isinstance(value, WorkbookLimits):
        return value
    if isinstance(value, Mapping):
        return WorkbookLimits(**dict(value))
    raise TypeError("limits must be WorkbookLimits, a mapping, or None")


def _display_raw(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, Decimal) and not value.is_finite():
        return str(value)
    return value


def _issue(
    row: ImportedHeaterRow,
    field: str,
    error_code: ErrorCode,
    message: str,
    suggested_fix: str,
    raw_value: Any,
) -> Issue:
    code_value = row.raw.code
    code = code_value if isinstance(code_value, str) and code_value else None
    return make_issue(
        error_code=error_code,
        severity=Severity.ERROR,
        message=message,
        suggested_fix=suggested_fix,
        scope=IssueScope.ROW,
        row_id=row.row_id,
        sheet=row.source.sheet,
        excel_row=row.source.excel_row,
        code=code,
        field=field,
        raw_value=_display_raw(raw_value),
        skippable=True,
    )


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _canonical_decimal(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"-0", ""} else text


def _parse_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or _is_missing(value):
        return None
    if isinstance(value, str):
        if ASCII_DECIMAL.fullmatch(value) is None:
            return None
        source = value
    elif isinstance(value, int):
        source = str(value)
    elif isinstance(value, float):
        if not math.isfinite(value):
            return None
        source = str(value)
    elif isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return value
    else:
        return None
    try:
        parsed = Decimal(source)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _code_problem(value: str) -> str | None:
    if any(unicodedata.category(character) == "Cc" for character in value):
        return "包含控制字符"
    if any(character in FORBIDDEN_FILENAME for character in value):
        return "包含跨平台文件名非法字符"
    if ".." in value:
        return "包含路径穿越片段 '..'"
    if value.endswith((".", " ")):
        return "以点或空格结尾"
    if value in {".", ".."}:
        return "不是有效文件名"
    if PureWindowsPath(value).is_reserved():
        return "使用了 Windows 保留名称"
    if len(value.encode("utf-8")) > 255:
        return "UTF-8 文件名超过 255 字节"
    return None


def validate_rows(
    rows: Iterable[ImportedHeaterRow],
    template: object | None = None,
    *,
    limits: WorkbookLimits | Mapping[str, Any] | None = None,
) -> ValidationResult:
    """Validate all non-geometric rules while preserving source row order."""

    del template  # Reserved for B04 geometry-dependent validation.
    configured = _limits(limits)
    source_rows = tuple(rows)
    issues: list[Issue] = []
    valid_rows: list[HeaterRow] = []
    duplicate_candidates: dict[str, list[ImportedHeaterRow]] = {}

    for row in source_rows:
        values: dict[str, Any] = {}
        row_issue_count = len(issues)
        unsupported_typed_fields: set[str] = set()

        for field in FIELD_ORDER:
            raw = getattr(row.raw, field)
            cell_type = row.cell_types.get(field)
            if cell_type == "e":
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 是 Excel 错误单元格，不能作为文字或数字读取",
                        "修正 Excel 错误后粘贴为静态文字或数字",
                        raw,
                    )
                )
                unsupported_typed_fields.add(field)
            elif cell_type == "d" or isinstance(raw, (datetime, date, time)):
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 是日期或时间单元格，不接受隐式文字转换",
                        "把业务文字明确设为文字，或为数字字段填写十进制数",
                        raw,
                    )
                )
                unsupported_typed_fields.add(field)

        for field in TEXT_FIELDS:
            if field in unsupported_typed_fields:
                continue
            raw = getattr(row.raw, field)
            if _is_missing(raw):
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.MISSING_FIELD,
                        f"{field} 为必填文字",
                        "填写非空文字后重新上传",
                        raw,
                    )
                )
            elif not isinstance(raw, str):
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 必须是文字，不能用数值代替",
                        "改为文字单元格后重新上传",
                        raw,
                    )
                )
            elif len(raw) > configured.max_text_characters:
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 超过 {configured.max_text_characters} 个 Unicode 字符",
                        "缩短文字且不要截断关键信息",
                        raw,
                    )
                )
            else:
                values[field] = raw

        raw_code = row.raw.code
        if "code" in unsupported_typed_fields:
            pass
        elif _is_missing(raw_code):
            issues.append(
                _issue(
                    row,
                    "code",
                    ErrorCode.MISSING_FIELD,
                    "code 为必填文字",
                    "填写批内唯一且可安全作为文件名的代号",
                    raw_code,
                )
            )
        elif not isinstance(raw_code, str):
            issues.append(
                _issue(
                    row,
                    "code",
                    ErrorCode.INVALID_FIELD,
                    "code 必须是文字",
                    "把代号单元格设为文字并填写安全代号",
                    raw_code,
                )
            )
        elif len(raw_code) > configured.max_text_characters:
            issues.append(
                _issue(
                    row,
                    "code",
                    ErrorCode.INVALID_FIELD,
                    f"code 超过 {configured.max_text_characters} 个 Unicode 字符",
                    "缩短代号",
                    raw_code,
                )
            )
        else:
            problem = _code_problem(raw_code)
            if problem:
                issues.append(
                    _issue(
                        row,
                        "code",
                        ErrorCode.INVALID_FIELD,
                        f"code {problem}",
                        "使用不含路径、控制符、保留名或非法字符的跨平台代号",
                        raw_code,
                    )
                )
            else:
                values["code"] = raw_code
            duplicate_candidates.setdefault(
                unicodedata.normalize("NFC", raw_code).casefold(), []
            ).append(row)

        numeric: dict[str, Decimal] = {}
        for field in NUMERIC_FIELDS:
            if field in unsupported_typed_fields:
                continue
            raw = getattr(row.raw, field)
            if _is_missing(raw):
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.MISSING_FIELD,
                        f"{field} 为必填数字",
                        "填写不使用指数、Unicode 数字、NaN 或 Inf 的十进制数",
                        raw,
                    )
                )
                continue
            parsed = _parse_decimal(raw)
            if parsed is None:
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 不是受支持的有限 ASCII 十进制数",
                        "使用 0-9 和可选小数点填写，不要使用指数、布尔值、NaN 或 Inf",
                        raw,
                    )
                )
                continue
            if field in POSITIVE_FIELDS and parsed <= 0:
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 必须大于 0",
                        "填写正有限数",
                        raw,
                    )
                )
                continue
            if field == "tolerance_ohm" and parsed < 0:
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        "tolerance_ohm 不能为负数",
                        "填写大于等于 0 的有限数",
                        raw,
                    )
                )
                continue
            try:
                exact_excel_numeric(parsed)
            except UnsupportedExcelNumeric:
                issues.append(
                    _issue(
                        row,
                        field,
                        ErrorCode.INVALID_FIELD,
                        f"{field} 无法由 XLSX 数值单元格精确保存",
                        "填写在 XLSX 数值精度和范围内可无损保存的十进制数",
                        raw,
                    )
                )
                continue
            numeric[field] = parsed
            values[field] = _canonical_decimal(parsed)

        if "width_mm" in numeric and "length_mm" in numeric:
            if numeric["width_mm"] > numeric["length_mm"]:
                issues.append(
                    _issue(
                        row,
                        "width_mm",
                        ErrorCode.INVALID_FIELD,
                        "width_mm 不能大于 length_mm",
                        "交换或修正宽度和长度，使宽度不大于长度",
                        row.raw.width_mm,
                    )
                )
        if "resistance_ohm" in numeric and "tolerance_ohm" in numeric:
            if numeric["tolerance_ohm"] > numeric["resistance_ohm"]:
                issues.append(
                    _issue(
                        row,
                        "tolerance_ohm",
                        ErrorCode.INVALID_FIELD,
                        "tolerance_ohm 不能大于 resistance_ohm",
                        "修正阻值偏差，使其不大于阻值",
                        row.raw.tolerance_ohm,
                    )
                )

        lead = row.raw.lead_side
        if "lead_side" in unsupported_typed_fields:
            pass
        elif _is_missing(lead):
            issues.append(
                _issue(
                    row,
                    "lead_side",
                    ErrorCode.MISSING_FIELD,
                    "lead_side 为必填字段",
                    "填写“短边”或“长边”",
                    lead,
                )
            )
        elif lead == "短边":
            values["lead_side"] = LeadSide.SHORT
        elif lead == "长边":
            values["lead_side"] = LeadSide.LONG
        else:
            issues.append(
                _issue(
                    row,
                    "lead_side",
                    ErrorCode.INVALID_FIELD,
                    "lead_side 只允许“短边”或“长边”",
                    "改为“短边”或“长边”",
                    lead,
                )
            )

        scale = row.raw.requested_scale
        if "requested_scale" in unsupported_typed_fields:
            pass
        elif _is_missing(scale):
            issues.append(
                _issue(
                    row,
                    "requested_scale",
                    ErrorCode.MISSING_FIELD,
                    "requested_scale 为必填字段",
                    "按 1:n 格式填写，且 n 大于等于 1",
                    scale,
                )
            )
        elif not isinstance(scale, str):
            issues.append(
                _issue(
                    row,
                    "requested_scale",
                    ErrorCode.INVALID_FIELD,
                    "requested_scale 必须是文字",
                    "按 1:n 格式填写，且 n 大于等于 1",
                    scale,
                )
            )
        elif len(scale) > configured.max_text_characters:
            issues.append(
                _issue(
                    row,
                    "requested_scale",
                    ErrorCode.INVALID_FIELD,
                    f"requested_scale 超过 {configured.max_text_characters} 个 Unicode 字符",
                    "缩短比例文字并按 1:n 格式填写",
                    scale,
                )
            )
        elif (match := SCALE.fullmatch(scale)) is None:
            issues.append(
                _issue(
                    row,
                    "requested_scale",
                    ErrorCode.INVALID_FIELD,
                    "requested_scale 必须是 ASCII 1:n 格式",
                    "按 1:n 格式填写，且 n 大于等于 1；不支持放大比例",
                    scale,
                )
            )
        else:
            denominator = Decimal(match.group(1))
            if not denominator.is_finite() or denominator < 1:
                issues.append(
                    _issue(
                        row,
                        "requested_scale",
                        ErrorCode.INVALID_FIELD,
                        "requested_scale 的分母必须大于等于 1",
                        "使用 1:1、1:2 等不放大的比例",
                        scale,
                    )
                )
            else:
                values["requested_scale"] = f"1:{_canonical_decimal(denominator)}"

        if len(issues) == row_issue_count:
            valid_rows.append(
                HeaterRow(
                    row_id=row.row_id,
                    source=row.source,
                    raw=row.raw,
                    values=HeaterFields(**values),
                )
            )

    for grouped in duplicate_candidates.values():
        if len(grouped) < 2:
            continue
        locations = ", ".join(str(row.source.excel_row) for row in grouped)
        for row in grouped:
            issues.append(
                _issue(
                    row,
                    "code",
                    ErrorCode.DUPLICATE_CODE,
                    f"代号按跨平台大小写折叠后重复，相关 Excel 行: {locations}",
                    "为所有相关行分配唯一代号，或在后续确认流程中明确选择保留行",
                    row.raw.code,
                )
            )

    field_rank = {field: index for index, field in enumerate(FIELD_ORDER)}
    issues.sort(
        key=lambda issue: (
            issue.excel_row if issue.excel_row is not None else 0,
            field_rank.get(issue.field or "", len(field_rank)),
            issue.error_code.value,
            str(issue.issue_id),
        )
    )
    return ValidationResult(source_rows, tuple(valid_rows), tuple(issues))
