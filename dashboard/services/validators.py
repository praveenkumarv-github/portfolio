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


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


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

    # Row-level negatives are not valid asset inputs and can desynchronize charts.
    for fund in data.get("mutual_funds", []) or []:
        current_value = _safe_float(fund.get("current_value", 0))
        if current_value < 0:
            warnings.append(
                f"Negative mutual fund value detected for {fund.get('fund_name', fund.get('identifier', '?'))} "
                f"({fund.get('identifier', '?')}): {current_value}"
            )

    for retirement in data.get("retirement", []) or []:
        amount = _safe_float(retirement.get("amount", 0))
        if amount < 0:
            warnings.append(
                f"Negative retirement amount detected for {retirement.get('type', '?')}: {amount}"
            )

    for liquid in data.get("liquid", []) or []:
        amount = _safe_float(liquid.get("amount", 0))
        if amount < 0:
            warnings.append(
                f"Negative liquid amount detected for {liquid.get('account_name', '?')}: {amount}"
            )

    for emergency in data.get("emergency_fund", []) or []:
        amount = _safe_float(emergency.get("amount", 0))
        if amount < 0:
            warnings.append(
                f"Negative emergency fund amount detected for {emergency.get('account_name', '?')}: {amount}"
            )

    for metal in data.get("metals", []) or []:
        amount = _safe_float(metal.get("value", 0))
        if amount < 0:
            warnings.append(
                f"Negative metals value detected for {metal.get('type', 'Metal')}: {amount}"
            )

    for policy in data.get("insurance", []) or []:
        premium = _safe_float(policy.get("premium", 0))
        coverage = _safe_float(policy.get("coverage", 0))
        if premium < 0:
            warnings.append(
                f"Negative insurance premium detected for {policy.get('type', '?')}: {premium}"
            )
        if coverage < 0:
            warnings.append(
                f"Negative insurance coverage detected for {policy.get('type', '?')}: {coverage}"
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

    # MFTransactions reconciliation: if a fund has a transaction ledger, its
    # net units (Invested - Redeemed) should match the declared holding
    # Units — otherwise invested-amount/gain/XIRR will be computed against
    # a partial or inconsistent ledger.
    txns_by_fund: Dict[str, float] = {}
    for txn in data.get("mf_transactions", []) or []:
        identifier = str(txn.get("identifier", ""))
        units = _safe_float(txn.get("units", 0))
        sign = 1.0 if txn.get("type") == "Invested" else -1.0
        txns_by_fund[identifier] = txns_by_fund.get(identifier, 0.0) + sign * units

    for fund in data.get("mutual_funds", []) or []:
        identifier = str(fund.get("identifier", ""))
        if identifier not in txns_by_fund:
            continue
        declared_units = _safe_float(fund.get("units", 0))
        ledger_units = txns_by_fund[identifier]
        tolerance = max(0.01, declared_units * 0.005)
        if abs(declared_units - ledger_units) > tolerance:
            warnings.append(
                f"MFTransactions for {fund.get('fund_name', identifier)} ({identifier}) sum to "
                f"{ledger_units:.2f} units but the MutualFunds sheet declares {declared_units:.2f} — "
                "invested amount and XIRR may be inaccurate until the ledger is complete."
            )

    return warnings
