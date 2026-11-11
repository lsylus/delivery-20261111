"""Versioned lead illustration rule in paper millimetres, independent of row IDs."""
from decimal import Decimal

RULE_ID = "short-edge-paper-v1"


def lead_parameters(width: Decimal, length: Decimal, denominator: Decimal, profile: dict) -> dict[str, Decimal]:
    if profile.get("rule_id") != RULE_ID:
        raise ValueError("unsupported lead illustration rule")
    if min(width, length, denominator) <= 0:
        raise ValueError("lead rule requires positive sizes and scale")
    short = min(width, length) / denominator
    result = {}
    for key in ("center_gap", "inside_length", "outside_length"):
        rule = profile[key]
        ratio, low, high = (Decimal(str(rule[k])) for k in ("ratio", "min_mm", "max_mm"))
        if not (0 < ratio <= 1 and 0 < low <= high):
            raise ValueError("invalid lead illustration limits")
        value = min(high, max(low, short * ratio))
        if "short_edge_cap" in rule:
            cap = Decimal(str(rule["short_edge_cap"]))
            if not 0 < cap < 1:
                raise ValueError("invalid short-edge lead cap")
            value = min(value, short * cap)
        result[key] = value
    return result
