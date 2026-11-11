"""The versioned 17-column Excel header contract."""

from __future__ import annotations

from typing import Final


FIELD_ORDER: Final[tuple[str, ...]] = (
    "name",
    "code",
    "width_mm",
    "length_mm",
    "lead_side",
    "resistance_ohm",
    "tolerance_ohm",
    "quantity_text",
    "requested_scale",
    "organization",
    "model",
    "designer",
    "checker",
    "reviewer",
    "standards_reviewer",
    "approver",
    "stage",
)

HEADER_BY_FIELD: Final[dict[str, str]] = {
    "name": "加热器名称",
    "code": "加热器代号",
    "width_mm": "加热器宽度\n（mm)",
    "length_mm": "加热器长度\n(mm)",
    "lead_side": "出线方向",
    "resistance_ohm": "阻值\n(Ω)",
    "tolerance_ohm": "阻值偏差(Ω)",
    "quantity_text": "投产数量",
    "requested_scale": "绘图比例",
    "organization": "单位名称",
    "model": "型号名称",
    "designer": "设计人员",
    "checker": "校对人员",
    "reviewer": "审核人员",
    "standards_reviewer": "标审人员",
    "approver": "批准人员",
    "stage": "阶段标记",
}

_PAREN_TRANSLATION = str.maketrans({"（": "(", "）": ")"})


def normalize_header(value: object) -> str | None:
    """Apply only the normalization explicitly allowed by R01."""

    if not isinstance(value, str):
        return None
    return value.replace("\r", "").replace("\n", "").strip().translate(
        _PAREN_TRANSLATION
    )


NORMALIZED_HEADER_TO_FIELD: Final[dict[str, str]] = {
    normalize_header(header): field
    for field, header in HEADER_BY_FIELD.items()
    if normalize_header(header) is not None
}


def headers_in_order() -> list[str]:
    return [HEADER_BY_FIELD[field] for field in FIELD_ORDER]
