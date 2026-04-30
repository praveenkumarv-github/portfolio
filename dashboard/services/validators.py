"""
Centralized Validation Layer
============================
Single place for schema and financial sanity checks.

Used by aggregator to attach warnings to the dashboard payload
without crashing the UI.
"""

from typing import Any, Dict, List


# Sanity bounds
NAV_MIN, NAV_MAX = 0.0, 10_000.0
GOLD_MIN, GOLD_MAX = 1_000.0, 200_000.0
SILVER_MIN, SILVER_MAX = 10.0, 5_000.0


def _bounds_for_metal(metal_type: str) -> tuple:
    m = (metal_type or "").strip().lower()
    if m == "gold":
        return GOLD_MIN, GOLD_MAX
    if m == "silver":
        return SILVER_MIN, SILVER_MAX
    return 0.0, float("inf")


def validate_portfolio_data(data: Dict[str, Any]) -> List[str]:
    """
    Validate parsed portfolio data and return a list of warning strings.

    Never raises. Never mutates input.
    """
    warnings: List[str] = []
    if not isinstance(data, dict):
        return ["Invalid portfolio data: not a dict"]

    # NAV bounds
    for fund in data.get("mutual_funds", []) or []:
        try:
            nav = float(fund.get("nav", 0) or 0)
        except (TypeError, ValueError):
            nav = 0.0
        if nav and not (NAV_MIN < nav < NAV_MAX):
            warnings.append(
                f"NAV out of bounds for {fund.get('fund_name', '?')} "
                f"({fund.get('identifier', '?')}): {nav}"
            )

    # Metal price bounds
    for metal in data.get("metals", []) or []:
        try:
            price = float(metal.get("price_per_gram", 0) or 0)
        except (TypeError, ValueError):
            price = 0.0
        lo, hi = _bounds_for_metal(metal.get("type", ""))
        if price and not (lo < price < hi):
            warnings.append(
                f"{metal.get('type', 'Metal')} price out of bounds: ₹{price:,.0f}/g"
            )

    # Non-negative totals
    for key in (
        "retirement_total",
        "liquid_total",
        "emergency_fund_total",
        "metals_total",
    ):
        try:
            val = float(data.get(key, 0) or 0)
        except (TypeError, ValueError):
            val = 0.0
        if val < 0:
            warnings.append(f"Negative total detected for {key}: {val}")

    mf_total = 0.0
    try:
        mf_total = float(
            (data.get("mutual_funds_summary") or {}).get("total_current_value", 0) or 0
        )
    except (TypeError, ValueError):
        pass
    if mf_total < 0:
        warnings.append(f"Negative mutual funds total: {mf_total}")

    return warnings
