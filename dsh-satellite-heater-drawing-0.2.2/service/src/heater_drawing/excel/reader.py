"""Bounded `.xlsx` reader that retains every populated source row."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import math
import posixpath
import re
import zlib
from typing import Any, Mapping
from xml.etree import ElementTree
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.utils import get_column_letter
from openpyxl.utils.exceptions import InvalidFileException

from heater_drawing.domain.errors import make_issue
from heater_drawing.domain.models import (
    ErrorCode,
    ImportedHeaterRow,
    Issue,
    IssueScope,
    RawHeaterFields,
    Severity,
    SourceLocation,
)
from heater_drawing.excel.headers import (
    FIELD_ORDER,
    NORMALIZED_HEADER_TO_FIELD,
    normalize_header,
)


CONTENT_TYPES_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/content-types"
)
PACKAGE_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
OFFICE_RELATIONSHIPS_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
SPREADSHEET_NAMESPACE = (
    "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
)
SHARED_STRINGS_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"
)
WORKBOOK_CONTENT_TYPES = (
    "application/vnd.ms-excel.template.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
    "application/vnd.ms-excel.sheet.macroEnabled.main+xml",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
)


@dataclass(frozen=True, slots=True)
class WorkbookLimits:
    max_file_bytes: int = 10 * 1024 * 1024
    max_business_rows: int = 500
    max_populated_rows_per_sheet: int = 501
    max_columns: int = 64
    max_zip_entries: int = 2000
    max_uncompressed_bytes: int = 100 * 1024 * 1024
    max_compression_ratio: float = 1000.0
    max_text_characters: int = 256

    def __post_init__(self) -> None:
        integer_limits = (
            "max_file_bytes",
            "max_business_rows",
            "max_populated_rows_per_sheet",
            "max_columns",
            "max_zip_entries",
            "max_uncompressed_bytes",
            "max_text_characters",
        )
        for name in integer_limits:
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        ratio = self.max_compression_ratio
        if (
            isinstance(ratio, bool)
            or not isinstance(ratio, (int, float))
            or not math.isfinite(ratio)
            or ratio <= 0
        ):
            raise ValueError("max_compression_ratio must be a positive finite number")
        if self.max_text_characters > 256:
            raise ValueError("max_text_characters cannot exceed 256")


@dataclass(frozen=True, slots=True)
class ParsedWorkbook:
    source_path: str
    source_sha256: str | None
    sheet: str
    rows: tuple[ImportedHeaterRow, ...]
    issues: tuple[Issue, ...]
    limits: WorkbookLimits

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)


class _WorkbookRejected(ValueError):
    def __init__(self, error_code: ErrorCode, message: str, suggested_fix: str):
        super().__init__(message)
        self.error_code = error_code
        self.suggested_fix = suggested_fix


def _coerce_limits(value: WorkbookLimits | Mapping[str, Any] | None) -> WorkbookLimits:
    if value is None:
        return WorkbookLimits()
    if isinstance(value, WorkbookLimits):
        return value
    if isinstance(value, Mapping):
        return WorkbookLimits(**dict(value))
    raise TypeError("limits must be WorkbookLimits, a mapping, or None")


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    return str(value)


def _workbook_issue(
    error_code: ErrorCode,
    message: str,
    suggested_fix: str,
    *,
    field: str | None = None,
    raw_value: Any | None = None,
    severity: Severity = Severity.ERROR,
) -> Issue:
    return make_issue(
        error_code=error_code,
        severity=severity,
        message=message,
        suggested_fix=suggested_fix,
        scope=IssueScope.WORKBOOK,
        field=field,
        raw_value=_json_safe_value(raw_value),
        skippable=False,
    )


def _row_issue(
    row: ImportedHeaterRow,
    error_code: ErrorCode,
    message: str,
    suggested_fix: str,
    *,
    field: str,
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
        raw_value=_json_safe_value(raw_value),
        skippable=True,
    )


def _safe_member_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not name.startswith(("/", "\\")) and "\\" not in name and ".." not in path.parts and ":" not in name


def _package_part_name(value: str) -> str:
    return value.removeprefix("/")


def _relationship_target(owner_part: str, target: str) -> str:
    if target.startswith("/"):
        resolved = target.removeprefix("/")
    else:
        resolved = posixpath.join(posixpath.dirname(owner_part), target)
    resolved = posixpath.normpath(resolved)
    if not _safe_member_name(resolved):
        raise _WorkbookRejected(
            ErrorCode.UNSUPPORTED_INPUT,
            f"XLSX 包含不安全关系目标: {target!r}",
            "使用 Excel 重新另存为标准 .xlsx 文件",
        )
    return resolved


def _content_type_maps(
    root: ElementTree.Element,
) -> tuple[dict[str, str], dict[str, str]]:
    defaults: dict[str, str] = {}
    overrides: dict[str, str] = {}
    for element in root:
        content_type = element.attrib.get("ContentType", "")
        if element.tag == f"{{{CONTENT_TYPES_NAMESPACE}}}Default":
            extension = element.attrib.get("Extension", "").casefold()
            if extension:
                defaults[extension] = content_type
        elif element.tag == f"{{{CONTENT_TYPES_NAMESPACE}}}Override":
            part = _package_part_name(element.attrib.get("PartName", ""))
            if part:
                overrides[part] = content_type
    return defaults, overrides


def _effective_content_type(
    part: str, defaults: Mapping[str, str], overrides: Mapping[str, str]
) -> str | None:
    if part in overrides:
        return overrides[part]
    extension = part.rpartition(".")[2].casefold()
    return defaults.get(extension)


def _relationships_part(owner_part: str) -> str:
    folder, filename = posixpath.split(owner_part)
    return posixpath.join(folder, "_rels", f"{filename}.rels")


def _active_workbook_part(
    archive: ZipFile, content_types: ElementTree.Element
) -> str:
    workbook_overrides = [
        element
        for content_type in WORKBOOK_CONTENT_TYPES
        for element in content_types.findall(
            f"{{{CONTENT_TYPES_NAMESPACE}}}Override"
        )
        if element.attrib.get("ContentType") == content_type
    ]
    if workbook_overrides:
        if len(workbook_overrides) != 1:
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 工作簿入口声明不唯一",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        declared_part = workbook_overrides[0].attrib.get("PartName", "")
        if not declared_part.startswith("/"):
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 工作簿入口路径无效",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        workbook_part = _package_part_name(declared_part)
    else:
        workbook_defaults = {
            element.attrib.get("ContentType")
            for element in content_types.findall(
                f"{{{CONTENT_TYPES_NAMESPACE}}}Default"
            )
            if element.attrib.get("ContentType") in WORKBOOK_CONTENT_TYPES
        }
        if len(workbook_defaults) != 1:
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 工作簿入口声明缺失或不唯一",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        workbook_part = "xl/workbook.xml"

    if not _safe_member_name(workbook_part) or workbook_part not in archive.namelist():
        raise _WorkbookRejected(
            ErrorCode.UNSUPPORTED_INPUT,
            "XLSX 工作簿入口部件缺失或路径无效",
            "使用 Excel 重新另存为标准 .xlsx 文件",
        )

    root_relationships = ElementTree.fromstring(archive.read("_rels/.rels"))
    office_document_parts = [
        _relationship_target("", element.attrib.get("Target", ""))
        for element in root_relationships.findall(
            f"{{{PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship"
        )
        if element.attrib.get("Type", "").endswith("/officeDocument")
    ]
    if office_document_parts != [workbook_part]:
        raise _WorkbookRejected(
            ErrorCode.UNSUPPORTED_INPUT,
            "XLSX 工作簿内容类型与根关系入口不一致",
            "使用 Excel 重新另存为标准 .xlsx 文件",
        )
    return workbook_part


def _workbook_relationships(
    archive: ZipFile, workbook_part: str
) -> dict[str, tuple[str, str]]:
    root = ElementTree.fromstring(
        archive.read(_relationships_part(workbook_part))
    )
    relationships: dict[str, tuple[str, str]] = {}
    for element in root.findall(
        f"{{{PACKAGE_RELATIONSHIPS_NAMESPACE}}}Relationship"
    ):
        relationship_id = element.attrib.get("Id", "")
        target = element.attrib.get("Target", "")
        if not relationship_id or not target or relationship_id in relationships:
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 工作簿关系定义无效",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        relationships[relationship_id] = (
            element.attrib.get("Type", ""),
            _relationship_target(workbook_part, target),
        )
    return relationships


def _consumed_worksheet_parts(
    archive: ZipFile,
    workbook_part: str,
    relationships: Mapping[str, tuple[str, str]],
) -> list[str]:
    workbook = ElementTree.fromstring(archive.read(workbook_part))
    relationship_id_attribute = f"{{{OFFICE_RELATIONSHIPS_NAMESPACE}}}id"
    parts: list[str] = []
    for sheet in workbook.iter(f"{{{SPREADSHEET_NAMESPACE}}}sheet"):
        relationship_id = sheet.attrib.get(relationship_id_attribute)
        if not relationship_id:
            continue
        if relationship_id not in relationships:
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 工作表关系缺失",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        relationship_type, target = relationships[relationship_id]
        if "chartsheet" not in relationship_type and target not in parts:
            parts.append(target)
    return parts


def _shared_string_index_is_in_range(value: str, count: int) -> bool:
    if re.fullmatch(r"[0-9]+", value, re.ASCII) is None or count == 0:
        return False
    normalized = value.lstrip("0") or "0"
    maximum = str(count - 1)
    return len(normalized) < len(maximum) or (
        len(normalized) == len(maximum) and normalized <= maximum
    )


def _inspect_shared_string_references(archive: ZipFile) -> None:
    try:
        content_types = ElementTree.fromstring(archive.read("[Content_Types].xml"))
        defaults, overrides = _content_type_maps(content_types)
        workbook_part = _active_workbook_part(archive, content_types)
        relationships = _workbook_relationships(archive, workbook_part)
        worksheet_parts = _consumed_worksheet_parts(
            archive, workbook_part, relationships
        )
        shared_parts = [
            name
            for name in archive.namelist()
            if _effective_content_type(name, defaults, overrides)
            == SHARED_STRINGS_CONTENT_TYPE
        ]
        related_shared_parts = [
            target
            for relationship_type, target in relationships.values()
            if relationship_type.endswith("/sharedStrings")
        ]
        if len(shared_parts) > 1:
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 包含多个共享字符串表",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        if len(set(related_shared_parts)) > 1 or (
            shared_parts
            and related_shared_parts
            and shared_parts[0] not in related_shared_parts
        ):
            raise _WorkbookRejected(
                ErrorCode.UNSUPPORTED_INPUT,
                "XLSX 共享字符串关系与内容类型不一致",
                "使用 Excel 重新另存为标准 .xlsx 文件",
            )
        if not shared_parts and related_shared_parts:
            shared_parts = [related_shared_parts[0]]
        shared_count = 0
        if shared_parts:
            shared_root = ElementTree.fromstring(archive.read(shared_parts[0]))
            shared_count = len(
                shared_root.findall(f"{{{SPREADSHEET_NAMESPACE}}}si")
            )
        for worksheet_part in worksheet_parts:
            worksheet = ElementTree.fromstring(archive.read(worksheet_part))
            for cell in worksheet.iter(f"{{{SPREADSHEET_NAMESPACE}}}c"):
                if cell.attrib.get("t") != "s":
                    continue
                reference = cell.attrib.get("r", "未知单元格")
                value_element = cell.find(f"{{{SPREADSHEET_NAMESPACE}}}v")
                value = value_element.text if value_element is not None else None
                if value is None or not _shared_string_index_is_in_range(
                    value, shared_count
                ):
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        f"XLSX 共享字符串引用无效: {worksheet_part}!{reference}",
                        "修复损坏的共享字符串引用，或使用 Excel 重新另存工作簿",
                    )
    except _WorkbookRejected:
        raise
    except (ElementTree.ParseError, KeyError) as exc:
        raise _WorkbookRejected(
            ErrorCode.UNSUPPORTED_INPUT,
            "XLSX 共享字符串或工作表结构损坏",
            "使用 Excel 重新另存为未损坏的 .xlsx 文件",
        ) from exc


def _inspect_package(data: bytes, limits: WorkbookLimits) -> None:
    try:
        with ZipFile(BytesIO(data)) as archive:
            members = archive.infolist()
            if len(members) > limits.max_zip_entries:
                raise _WorkbookRejected(
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    f"XLSX ZIP 条目数 {len(members)} 超过限制 {limits.max_zip_entries}",
                    "移除无关嵌入内容后重新上传 .xlsx 文件",
                )
            names: set[str] = set()
            declared_total = 0
            for member in members:
                if not _safe_member_name(member.filename):
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        f"XLSX 包含不安全路径: {member.filename!r}",
                        "使用 Excel 重新另存为标准 .xlsx 文件",
                    )
                if member.filename in names:
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        f"XLSX 包含重复 ZIP 条目: {member.filename}",
                        "使用 Excel 重新另存为标准 .xlsx 文件",
                    )
                names.add(member.filename)
                if member.flag_bits & 0x1:
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        "不支持加密的 XLSX ZIP 条目",
                        "移除工作簿加密后重新上传",
                    )
                if member.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        "XLSX 使用了不支持的 ZIP 压缩方法",
                        "使用 Excel 重新另存为标准 .xlsx 文件",
                    )
                declared_total += member.file_size
                ratio = member.file_size / max(member.compress_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise _WorkbookRejected(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        f"XLSX 条目压缩比 {ratio:.1f} 超过限制 {limits.max_compression_ratio:g}",
                        "移除异常压缩或嵌入内容后重新上传",
                    )
            if declared_total > limits.max_uncompressed_bytes:
                raise _WorkbookRejected(
                    ErrorCode.PAYLOAD_TOO_LARGE,
                    f"XLSX 声明解压总量 {declared_total} 字节超过限制 {limits.max_uncompressed_bytes}",
                    "缩减工作簿内容后重新上传",
                )

            required = {"[Content_Types].xml", "_rels/.rels"}
            if not required.issubset(names):
                raise _WorkbookRejected(
                    ErrorCode.UNSUPPORTED_INPUT,
                    "文件不是完整的 XLSX 工作簿包",
                    "上传由 Excel 或兼容软件生成的标准 .xlsx 文件",
                )
            lowered = {name.casefold() for name in names}
            if "xl/vbaproject.bin" in lowered or any(
                name.startswith("xl/externallinks/") for name in lowered
            ):
                raise _WorkbookRejected(
                    ErrorCode.UNSUPPORTED_INPUT,
                    "不支持宏或外部工作簿链接",
                    "移除宏和外部链接后另存为 .xlsx",
                )

            actual_total = 0
            for member in members:
                if member.is_dir():
                    continue
                with archive.open(member) as source:
                    while chunk := source.read(1024 * 1024):
                        actual_total += len(chunk)
                        if actual_total > limits.max_uncompressed_bytes:
                            raise _WorkbookRejected(
                                ErrorCode.PAYLOAD_TOO_LARGE,
                                "XLSX 实际解压总量超过限制",
                                "缩减工作簿内容后重新上传",
                            )

            for member in members:
                if not member.filename.endswith(".rels"):
                    continue
                try:
                    root = ElementTree.fromstring(archive.read(member))
                except ElementTree.ParseError as exc:
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        f"XLSX 关系文件损坏: {member.filename}",
                        "使用 Excel 重新另存工作簿",
                    ) from exc
                if any(
                    element.attrib.get("TargetMode", "").casefold() == "external"
                    for element in root
                ):
                    raise _WorkbookRejected(
                        ErrorCode.UNSUPPORTED_INPUT,
                        "不支持 XLSX 外部关系",
                        "移除外部链接后另存为 .xlsx",
                    )
            _inspect_shared_string_references(archive)
    except BadZipFile as exc:
        raise _WorkbookRejected(
            ErrorCode.UNSUPPORTED_INPUT,
            "文件不是有效的 XLSX ZIP 包或已经损坏",
            "重新导出并上传未损坏的 .xlsx 文件",
        ) from exc


def _cell_has_content(cell: Cell) -> bool:
    if cell.data_type == "f":
        return True
    value = cell.value
    return value is not None and not (isinstance(value, str) and value == "")


def _material_cells(sheet: Any) -> list[Cell]:
    return [
        cell
        for cell in sheet._cells.values()  # openpyxl's loaded sparse cell store
        if isinstance(cell, Cell) and _cell_has_content(cell)
    ]


def _check_sheet_limits(workbook: Any, limits: WorkbookLimits) -> None:
    for sheet in workbook.worksheets:
        material = _material_cells(sheet)
        populated_rows = {cell.row for cell in material}
        if len(populated_rows) > limits.max_populated_rows_per_sheet:
            raise _WorkbookRejected(
                ErrorCode.PAYLOAD_TOO_LARGE,
                f"工作表 {sheet.title!r} 的非空行数超过限制 {limits.max_populated_rows_per_sheet}",
                "删除无关数据行或拆分工作簿后重新上传",
            )
        if material and max(cell.column for cell in material) > limits.max_columns:
            raise _WorkbookRejected(
                ErrorCode.PAYLOAD_TOO_LARGE,
                f"工作表 {sheet.title!r} 的非空列超出第 {limits.max_columns} 列限制",
                "删除远端无关列后重新上传",
            )


def _parse_headers(sheet: Any) -> tuple[dict[int, str], list[Issue]]:
    mapped: dict[int, str] = {}
    fields_to_columns: dict[str, list[int]] = {}
    issues: list[Issue] = []
    material = _material_cells(sheet)
    max_column = max((cell.column for cell in material), default=17)
    populated_below_header = {
        cell.column for cell in material if cell.row >= 2
    }
    for column in range(1, max_column + 1):
        cell = sheet.cell(1, column)
        if not _cell_has_content(cell):
            if column in populated_below_header:
                issues.append(
                    _workbook_issue(
                        ErrorCode.INVALID_FIELD,
                        f"未命名列 {sheet.title}!{get_column_letter(column)}1 下方含业务值",
                        "删除该列数据，或填写契约规定的固定表头",
                        raw_value=f"{sheet.title}!{get_column_letter(column)}1",
                    )
                )
            continue
        coordinate = f"{sheet.title}!{get_column_letter(column)}1"
        if cell.data_type == "f":
            issues.append(
                _workbook_issue(
                    ErrorCode.UNSUPPORTED_INPUT,
                    f"表头 {coordinate} 是公式，不读取公式或缓存值",
                    "把表头改为契约中的固定文字",
                    raw_value=cell.value,
                )
            )
            continue
        normalized = normalize_header(cell.value)
        field = NORMALIZED_HEADER_TO_FIELD.get(normalized or "")
        if field is None:
            issues.append(
                _workbook_issue(
                    ErrorCode.INVALID_FIELD,
                    f"未知表头 {coordinate}: {cell.value!r}",
                    "删除未知列或改为契约规定的 17 个表头之一",
                    raw_value=cell.value,
                )
            )
            continue
        mapped[column] = field
        fields_to_columns.setdefault(field, []).append(column)

    for field in FIELD_ORDER:
        columns = fields_to_columns.get(field, [])
        if not columns:
            issues.append(
                _workbook_issue(
                    ErrorCode.MISSING_FIELD,
                    f"缺少必需表头: {field}",
                    "补充对应的固定表头后重新上传",
                    field=field,
                )
            )
        elif len(columns) > 1:
            coordinates = [f"{get_column_letter(column)}1" for column in columns]
            issues.append(
                _workbook_issue(
                    ErrorCode.INVALID_FIELD,
                    f"表头 {field} 重复出现在 {', '.join(coordinates)}",
                    "每个必需字段只保留一列",
                    field=field,
                    raw_value=coordinates,
                )
            )
    return mapped, issues


def _has_populated_merge(sheet: Any) -> str | None:
    for merged in sheet.merged_cells.ranges:
        top_left = sheet.cell(merged.min_row, merged.min_col)
        if _cell_has_content(top_left):
            return str(merged)
    return None


def parse_workbook(
    path: str | Path,
    limits: WorkbookLimits | Mapping[str, Any] | None = None,
) -> ParsedWorkbook:
    """Parse `Sheet1` without evaluating formulas or dropping invalid rows."""

    configured = _coerce_limits(limits)
    source = Path(path)
    digest: str | None = None
    issues: list[Issue] = []
    if source.suffix.casefold() != ".xlsx":
        issues.append(
            _workbook_issue(
                ErrorCode.UNSUPPORTED_INPUT,
                "只支持 .xlsx 文件",
                "将工作簿另存为 .xlsx 后重新上传",
                raw_value=source.name,
            )
        )
        return ParsedWorkbook(str(source), None, "Sheet1", (), tuple(issues), configured)
    try:
        data = source.read_bytes()
        digest = sha256(data).hexdigest()
        if len(data) > configured.max_file_bytes:
            raise _WorkbookRejected(
                ErrorCode.PAYLOAD_TOO_LARGE,
                f"文件大小 {len(data)} 字节超过限制 {configured.max_file_bytes}",
                "缩减文件到限制以内后重新上传",
            )
        _inspect_package(data, configured)
        workbook = load_workbook(
            BytesIO(data),
            read_only=False,
            data_only=False,
            keep_links=False,
        )
        try:
            _check_sheet_limits(workbook, configured)
            if "Sheet1" not in workbook.sheetnames:
                raise _WorkbookRejected(
                    ErrorCode.MISSING_FIELD,
                    "缺少指定工作表 Sheet1",
                    "把 17 字段数据放入名为 Sheet1 的工作表",
                )
            sheet = workbook["Sheet1"]
            for other in workbook.worksheets:
                if other.title != "Sheet1" and _material_cells(other):
                    issues.append(
                        _workbook_issue(
                            ErrorCode.UNSUPPORTED_INPUT,
                            f"工作表 {other.title!r} 含数据但未处理",
                            "把需要导入的数据移到 Sheet1；其他工作表不会导入",
                            raw_value=other.title,
                            severity=Severity.WARNING,
                        )
                    )
            merged = _has_populated_merge(sheet)
            if merged is not None:
                issues.append(
                    _workbook_issue(
                        ErrorCode.UNSUPPORTED_INPUT,
                        f"Sheet1 包含已填值的合并单元格 {merged}",
                        "取消业务区域的单元格合并后重新上传",
                        raw_value=merged,
                    )
                )
            column_to_field, header_issues = _parse_headers(sheet)
            issues.extend(header_issues)

            material_rows = sorted(
                {
                    cell.row
                    for cell in _material_cells(sheet)
                    if cell.row >= 2
                }
            )
            if len(material_rows) > configured.max_business_rows:
                issues.append(
                    _workbook_issue(
                        ErrorCode.PAYLOAD_TOO_LARGE,
                        f"非空业务行 {len(material_rows)} 条超过限制 {configured.max_business_rows}",
                        "拆分为不超过限制的工作簿后重新上传",
                        raw_value=len(material_rows),
                    )
                )

            rows: list[ImportedHeaterRow] = []
            field_to_column: dict[str, int] = {}
            for column, field in column_to_field.items():
                field_to_column.setdefault(field, column)
            for excel_row in material_rows:
                raw_values = {
                    field: sheet.cell(excel_row, field_to_column[field]).value
                    if field in field_to_column
                    else None
                    for field in FIELD_ORDER
                }
                cell_types = {
                    field: sheet.cell(excel_row, field_to_column[field]).data_type
                    for field in FIELD_ORDER
                    if field in field_to_column
                }
                imported = ImportedHeaterRow(
                    row_id=f"Sheet1:{excel_row}",
                    source=SourceLocation(sheet="Sheet1", excel_row=excel_row),
                    raw=RawHeaterFields(**raw_values),
                    cell_types=cell_types,
                )
                rows.append(imported)
                for field, column in field_to_column.items():
                    cell = sheet.cell(excel_row, column)
                    if cell.data_type == "f":
                        issues.append(
                            _row_issue(
                                imported,
                                ErrorCode.UNSUPPORTED_INPUT,
                                f"单元格 {cell.coordinate} 是公式，不执行公式也不读取缓存值",
                                "把公式结果粘贴为静态值后重新上传",
                                field=field,
                                raw_value=cell.value,
                            )
                        )
            return ParsedWorkbook(
                str(source), digest, "Sheet1", tuple(rows), tuple(issues), configured
            )
        finally:
            workbook.close()
    except FileNotFoundError:
        issues.append(
            _workbook_issue(
                ErrorCode.NOT_FOUND,
                "输入工作簿不存在",
                "确认文件路径后重新上传",
                raw_value=str(source),
            )
        )
    except PermissionError:
        issues.append(
            _workbook_issue(
                ErrorCode.ACCESS_DENIED,
                "没有权限读取输入工作簿",
                "检查文件权限后重新上传",
                raw_value=str(source),
            )
        )
    except _WorkbookRejected as exc:
        issues.append(
            _workbook_issue(
                exc.error_code,
                str(exc),
                exc.suggested_fix,
            )
        )
    except (
        BadZipFile,
        EOFError,
        InvalidFileException,
        IndexError,
        KeyError,
        OSError,
        ValueError,
        ElementTree.ParseError,
        zlib.error,
    ) as exc:
        issues.append(
            _workbook_issue(
                ErrorCode.UNSUPPORTED_INPUT,
                f"无法解析 XLSX 工作簿: {type(exc).__name__}",
                "使用 Excel 重新另存为未损坏的 .xlsx 文件",
            )
        )
    return ParsedWorkbook(str(source), digest, "Sheet1", (), tuple(issues), configured)
