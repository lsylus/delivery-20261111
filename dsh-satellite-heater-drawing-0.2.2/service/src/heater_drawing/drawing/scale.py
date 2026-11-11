"""Versioned scale parsing and recommendation helpers."""

from __future__ import annotations

from decimal import Decimal

from heater_drawing.domain.models import Scale

from .geometry import decimal_text


def make_scale(denominator: Decimal | str | int) -> Scale:
    value = Decimal(str(denominator))
    text = decimal_text(value)
    return Scale(denominator=text, label=f"1:{text}")


def recommendation_denominators(original: Scale, layout: dict) -> tuple[Decimal, ...]:
    current = Decimal(original.denominator)
    configured = tuple(Decimal(str(value)) for value in layout["standard_scale_denominators"])
    if tuple(sorted(set(configured))) != configured or any(value < 1 for value in configured):
        raise ValueError("standard scale denominator profile is invalid")
    return tuple(value for value in configured if value > current)
