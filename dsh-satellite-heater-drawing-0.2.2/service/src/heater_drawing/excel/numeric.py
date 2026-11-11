"""Exact numeric conversion shared by validation and XLSX writing."""

from __future__ import annotations

from decimal import Decimal, DecimalException

from openpyxl.compat import safe_string


class UnsupportedExcelNumeric(ValueError):
    """A decimal cannot be represented exactly as an XLSX numeric cell."""


def exact_excel_numeric(value: Decimal | str) -> int | float:
    """Return the openpyxl value only when its serialized decimal is exact."""

    try:
        value = value if isinstance(value, Decimal) else Decimal(value)
        if not value.is_finite():
            raise UnsupportedExcelNumeric(
                "XLSX numeric cells require a finite decimal"
            )
        if value.is_zero():
            return 0
        if value.adjusted() > 308:
            raise UnsupportedExcelNumeric(
                "decimal is outside the XLSX numeric representation"
            )
        digits = value.as_tuple().digits
        significant_digits = len(digits)
        while significant_digits > 1 and digits[significant_digits - 1] == 0:
            significant_digits -= 1
        if significant_digits > 15:
            raise UnsupportedExcelNumeric(
                "decimal exceeds Excel's 15-significant-digit numeric precision"
            )
        excel_value: int | float
        if value == value.to_integral_value():
            excel_value = int(value)
        else:
            excel_value = float(value)
        serialized = safe_string(excel_value)
        round_tripped = Decimal(serialized)
    except UnsupportedExcelNumeric:
        raise
    except (
        DecimalException,
        OverflowError,
        TypeError,
        ValueError,
    ) as exc:
        raise UnsupportedExcelNumeric(
            "decimal is outside the XLSX numeric representation"
        ) from exc
    if round_tripped != value:
        raise UnsupportedExcelNumeric(
            f"XLSX numeric serialization would change {value} to {serialized}"
        )
    return excel_value
