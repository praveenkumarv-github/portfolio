"""
Alerts Engine
=============
Analyses parsed portfolio data and produces actionable warnings.

Rules implemented:
  1. Emergency fund < 6 months of monthly expenses (derived from insurance premiums)
     → uses a configurable monthly_expense estimate or falls back to total/6 heuristic
  2. Single asset class > 60% of net worth → over-concentration warning
  3. Any NAV sourced from "Default" or "Not Available" → data quality alert
  4. Any metal price sourced from "Default" → data quality alert
  5. Zero net worth → no data loaded yet (info)

Each alert is a dict:
  {
    "level":   "error" | "warning" | "info",
    "code":    str,           # machine-readable key
    "message": str,           # human-readable for dashboard
  }
"""

from typing import Dict, Any, List


# Monthly expense estimate when none is available.
# Change this to reflect actual household expenses.
DEFAULT_MONTHLY_EXPENSE = 50_000.0   # ₹50,000/month


def _pct(part: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return (part / total) * 100


def run_alerts(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Analyse portfolio data and return a list of alerts.

    Parameters
    ----------
    data : dict
        The ``result["data"]`` dict returned by ``parse_excel_file``.

    Returns
    -------
    list of alert dicts  (may be empty)
    """
    alerts: List[Dict[str, str]] = []
    metrics = data.get("global_metrics", {})
    nw = float(metrics.get("total_net_worth", 0))

    # ── Alert 1: empty portfolio ──────────────────────────────────────
    if nw <= 0:
        alerts.append({
            "level":   "info",
            "code":    "NO_DATA",
            "message": "No portfolio data loaded. Upload your Excel file.",
        })
        return alerts   # nothing else makes sense without data

    # ── Alert 2: emergency fund coverage ─────────────────────────────
    ef_total = float(data.get("emergency_fund_total", 0))
    # Try to derive monthly expenses from insurance premiums (annual → monthly)
    insurance = data.get("insurance_summary", {})
    annual_premium = float(insurance.get("total_premium", 0))
    if annual_premium > 0:
        monthly_expense = annual_premium / 12
    else:
        monthly_expense = DEFAULT_MONTHLY_EXPENSE

    ef_months = ef_total / monthly_expense if monthly_expense > 0 else 0
    if ef_months < 3:
        alerts.append({
            "level":   "error",
            "code":    "EF_CRITICAL",
            "message": (
                f"Emergency fund covers only {ef_months:.1f} months of expenses "
                f"(₹{ef_total:,.0f} ÷ ₹{monthly_expense:,.0f}/mo). "
                "Target: 6 months minimum."
            ),
        })
    elif ef_months < 6:
        alerts.append({
            "level":   "warning",
            "code":    "EF_LOW",
            "message": (
                f"Emergency fund covers {ef_months:.1f} months of expenses. "
                "Recommended: 6 months."
            ),
        })

    # ── Alert 3: over-concentration ───────────────────────────────────
    allocation = {
        "Mutual Funds" : float(data.get("mutual_funds_summary", {}).get("total_current_value", 0)),
        "Retirement"   : float(data.get("retirement_total", 0)),
        "Liquid"       : float(data.get("liquid_total", 0)),
        "Emergency Fund": float(data.get("emergency_fund_total", 0)),
        "Metals"       : float(data.get("metals_total", 0)),
    }
    for category, amount in allocation.items():
        pct = _pct(amount, nw)
        if pct > 60:
            alerts.append({
                "level":   "warning",
                "code":    "OVER_CONCENTRATION",
                "message": (
                    f"{category} represents {pct:.1f}% of net worth. "
                    "Consider rebalancing — recommended max: 60% in any single category."
                ),
            })

    # ── Alert 4: data quality — NAV sources ───────────────────────────
    for fund in data.get("mutual_funds", []):
        src = fund.get("nav_source", "")
        if "Not Available" in src or "Default" in src or fund.get("nav", 0) == 0:
            alerts.append({
                "level":   "warning",
                "code":    "NAV_MISSING",
                "message": (
                    f"NAV unavailable for {fund.get('fund_name', fund.get('identifier', '?'))} "
                    f"({fund.get('identifier', '?')}). Current value shown as ₹0."
                ),
            })

    # ── Alert 5: data quality — metal price sources ───────────────────
    for metal in data.get("metals", []):
        src = metal.get("price_source", "")
        if "Default" in src:
            alerts.append({
                "level":   "warning",
                "code":    "METAL_DEFAULT_PRICE",
                "message": (
                    f"{metal.get('type', 'Metal')} price is using a hard-coded default "
                    f"(₹{metal.get('price_per_gram', 0):,.0f}/g). "
                    "Live fetch failed — use the manual override or check connectivity."
                ),
            })

    return alerts
