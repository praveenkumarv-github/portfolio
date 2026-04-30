"""
Calculation Engine
==================
Single source of truth for all portfolio aggregations, percentages,
and derived metrics.  No business logic lives in views.py or templates.

FINANCIAL RULES:
  - Insurance is NOT an asset. It is excluded from net worth, allocation
    charts, and all % calculations.
  - net_worth = mutual_funds + retirement + liquid + emergency_fund + metals
  - Insurance data lives separately under risk_data / risk_rows.

Public API
----------
build_portfolio(data: dict) -> PortfolioSummary
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------

@dataclass
class CategoryRow:
    key: str
    label: str
    icon: str
    value: float
    pct: float = 0.0
    meta: str = ""
    alert_level: str = ""   # "" | "ok" | "warn" | "error"


@dataclass
class RiskRow:
    type: str
    provider: str
    coverage: float
    premium: float
    status: str      # "Adequate" | "Review" | "Low"
    status_level: str  # "ok" | "warn" | "error"


@dataclass
class PortfolioSummary:
    # Core financials (insurance excluded)
    net_worth: float
    mf_total: float
    retirement_total: float
    liquid_total: float
    emergency_fund_total: float
    metals_total: float
    liquid_plus_ef: float

    # Asset categories (no insurance)
    categories: List[CategoryRow]

    # Charts (assets only)
    allocation_chart: dict   # {labels, values, colours}
    category_comparison_meta: dict  # {largest, underweight}

    # Per-blade mini-chart data (assets only)
    mf_chart: dict
    mf_split: List[dict]
    mf_split_chart: dict
    liquid_chart: dict
    ef_chart: dict
    metals_chart: dict
    risk_chart: dict

    # Detail rows
    mutual_funds: List[dict]
    retirement: List[dict]
    liquid: List[dict]
    emergency_fund: List[dict]
    emergency_fund_by_type: dict
    metals: List[dict]

    # Risk / insurance (separate from assets)
    risk_rows: List[RiskRow]
    risk_summary: dict       # {total_coverage, total_premium, policy_count, monthly_expense}

    has_data: bool = True


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ASSET_KEYS = [
    ("mutual_funds",   "Mutual Funds",   "📈", "#4f8ef7"),
    ("retirement",     "Retirement",     "🏦", "#7c5cf6"),
    ("liquid",         "Liquid",         "💵", "#2dd4a0"),
    ("emergency_fund", "Emergency Fund", "🚨", "#f06b6b"),
    ("metals",         "Metals",         "🪙", "#e8b44a"),
]

_LIFE_COVERAGE_MIN = 5_000_000   # ₹50 L minimum life coverage considered adequate
_HEALTH_COVERAGE_MIN = 500_000   # ₹5 L minimum health coverage per policy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pct(part: float, total: float) -> float:
    return round((part / total) * 100, 1) if total > 0 else 0.0


def _ef_alert(ef_total: float, monthly_expense: float) -> str:
    months = ef_total / monthly_expense if monthly_expense > 0 else 0
    if months < 3:
        return "error"
    if months < 6:
        return "warn"
    return "ok"


def _insurance_status(policy: dict) -> tuple:
    """Return (status_label, status_level) for a single insurance policy."""
    itype    = str(policy.get("type", "")).lower()
    coverage = float(policy.get("coverage", 0))
    if "life" in itype or "term" in itype:
        if coverage >= _LIFE_COVERAGE_MIN:
            return "Adequate", "ok"
        elif coverage > 0:
            return "Review", "warn"
        return "Low", "error"
    elif "health" in itype or "medical" in itype:
        if coverage >= _HEALTH_COVERAGE_MIN:
            return "Adequate", "ok"
        elif coverage > 0:
            return "Review", "warn"
        return "Low", "error"
    return "Check", "warn"


def _mini_chart(labels: List[str], values: List[float], colours: List[str]) -> dict:
    """Filter out zero-value entries and return chart-ready dict."""
    out_l, out_v, out_c = [], [], []
    for l, v, c in zip(labels, values, colours):
        if v > 0:
            out_l.append(l)
            out_v.append(v)
            out_c.append(c)
    return {"labels": out_l, "values": out_v, "colours": out_c}


def _classify_fund_type(fund: dict) -> str:
    """Classify a mutual fund into Equity/Debt/Hybrid using type or name hints."""
    direct = str(fund.get("fund_type", "")).strip().lower()
    if direct:
        if "equity" in direct:
            return "Equity"
        if "debt" in direct or "bond" in direct or "income" in direct:
            return "Debt"
        if "hybrid" in direct or "balanced" in direct or "arbitrage" in direct:
            return "Hybrid"

    name = str(fund.get("fund_name", "")).lower()
    equity_keys = (
        "equity", "elss", "small cap", "mid cap", "large cap", "index",
        "flexi", "multi cap", "thematic", "sector", "value", "growth",
    )
    debt_keys = (
        "debt", "bond", "income", "gilt", "liquid", "money market",
        "corporate", "short duration", "ultra short", "credit risk",
    )
    hybrid_keys = (
        "hybrid", "balanced", "asset allocation", "arbitrage", "multi asset",
        "dynamic asset", "conservative", "aggressive",
    )

    if any(k in name for k in equity_keys):
        return "Equity"
    if any(k in name for k in debt_keys):
        return "Debt"
    if any(k in name for k in hybrid_keys):
        return "Hybrid"
    return "Hybrid"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_portfolio(data: dict) -> PortfolioSummary:
    # ── Raw totals ────────────────────────────────────────────────────────
    mf_total  = float(data.get("mutual_funds_summary", {}).get("total_current_value", 0))
    ret_total = float(data.get("retirement_total", 0))
    liq_total = float(data.get("liquid_total", 0))
    ef_total  = float(data.get("emergency_fund_total", 0))
    met_total = float(data.get("metals_total", 0))

    ins_prem  = float(data.get("insurance_summary", {}).get("total_premium", 0))
    ins_cov   = float(data.get("insurance_summary", {}).get("total_coverage", 0))

    # net_worth = assets only (insurance excluded)
    net_worth = mf_total + ret_total + liq_total + ef_total + met_total

    monthly_expense = max(ins_prem / 12, 50_000.0) if ins_prem > 0 else 50_000.0

    # ── Asset category rows ───────────────────────────────────────────────
    _vals = {
        "mutual_funds":   mf_total,
        "retirement":     ret_total,
        "liquid":         liq_total,
        "emergency_fund": ef_total,
        "metals":         met_total,
    }

    categories: List[CategoryRow] = []
    chart_labels, chart_values, chart_colours = [], [], []

    for key, label, icon, colour in _ASSET_KEYS:
        val = _vals[key]
        pct = _pct(val, net_worth)

        if key == "mutual_funds":
            fc = len(data.get("mutual_funds", []))
            meta = f"{fc} fund{'s' if fc != 1 else ''}"
            alert = "warn" if pct > 70 else ""
        elif key == "retirement":
            meta = f"{len(data.get('retirement', []))} instrument(s)"
            alert = ""
        elif key == "liquid":
            meta = f"{len(data.get('liquid', []))} account(s)"
            alert = ""
        elif key == "emergency_fund":
            months = ef_total / monthly_expense if monthly_expense > 0 else 0
            meta = f"{months:.1f} mo coverage"
            alert = _ef_alert(ef_total, monthly_expense)
        else:  # metals
            meta = f"{len(data.get('metals', []))} type(s)"
            alert = ""

        categories.append(CategoryRow(
            key=key, label=label, icon=icon,
            value=val, pct=pct, meta=meta, alert_level=alert,
        ))
        if val > 0:
            chart_labels.append(label)
            chart_values.append(val)
            chart_colours.append(colour)

    positive_assets = [(c.label, c.value, c.pct) for c in categories if c.value > 0]
    if positive_assets:
        largest = max(positive_assets, key=lambda x: x[1])
        underweight = min(positive_assets, key=lambda x: x[1])
        category_comparison_meta = {
            "largest": {
                "label": largest[0],
                "value": largest[1],
                "pct": largest[2],
            },
            "underweight": {
                "label": underweight[0],
                "value": underweight[1],
                "pct": underweight[2],
            },
        }
    else:
        category_comparison_meta = {"largest": None, "underweight": None}

    # ── Per-blade mini charts ─────────────────────────────────────────────
    mf_list = data.get("mutual_funds", [])
    mf_chart = _mini_chart(
        [f.get("fund_name", "Fund")[:20] for f in mf_list],
        [float(f.get("current_value", 0)) for f in mf_list],
        [f"hsl({(i*47)%360},60%,55%)" for i in range(len(mf_list))],
    )

    mf_split_totals = {"Equity": 0.0, "Debt": 0.0, "Hybrid": 0.0}
    for fund in mf_list:
        bucket = _classify_fund_type(fund)
        mf_split_totals[bucket] += float(fund.get("current_value", 0))
    mf_split = []
    for label in ("Equity", "Debt", "Hybrid"):
        val = mf_split_totals[label]
        pct = _pct(val, mf_total)
        mf_split.append({"type": label, "value": val, "pct": pct})
    mf_split_chart = _mini_chart(
        [x["type"] for x in mf_split],
        [x["value"] for x in mf_split],
        ["#4f8ef7", "#7c5cf6", "#34c79a"],
    )

    liq_list = data.get("liquid", [])
    liq_chart = _mini_chart(
        [a.get("account_name", "Account") for a in liq_list],
        [float(a.get("amount", 0)) for a in liq_list],
        [f"hsl({(i*67+120)%360},55%,50%)" for i in range(len(liq_list))],
    )

    ef_bt = data.get("emergency_fund_by_type", {})
    ef_chart = _mini_chart(
        list(ef_bt.keys()),
        [float(v) for v in ef_bt.values()],
        ["#f06b6b", "#fb923c", "#fbbf24", "#34d399", "#60a5fa"],
    )

    met_list = data.get("metals", [])
    metals_chart = _mini_chart(
        [m.get("type", "Metal") for m in met_list],
        [float(m.get("value", 0)) for m in met_list],
        ["#e8b44a", "#90a8be"],
    )

    ret_list = data.get("retirement", [])

    # ── Risk / insurance ──────────────────────────────────────────────────
    risk_rows: List[RiskRow] = []
    for pol in data.get("insurance", []):
        status, level = _insurance_status(pol)
        risk_rows.append(RiskRow(
            type=pol.get("type", ""),
            provider=pol.get("provider", ""),
            coverage=float(pol.get("coverage", 0)),
            premium=float(pol.get("premium", 0)),
            status=status,
            status_level=level,
        ))

    risk_summary = {
        "total_coverage":    ins_cov,
        "total_premium":     ins_prem,
        "policy_count":      len(risk_rows),
        "monthly_expense":   monthly_expense,
    }

    risk_chart = _mini_chart(
        [row.type or "Policy" for row in risk_rows],
        [row.coverage for row in risk_rows],
        [f"hsl({(i*61+300)%360},50%,58%)" for i in range(len(risk_rows))],
    )

    return PortfolioSummary(
        net_worth=net_worth,
        mf_total=mf_total,
        retirement_total=ret_total,
        liquid_total=liq_total,
        emergency_fund_total=ef_total,
        metals_total=met_total,
        liquid_plus_ef=liq_total + ef_total,
        categories=categories,
        allocation_chart={"labels": chart_labels, "values": chart_values, "colours": chart_colours},
        category_comparison_meta=category_comparison_meta,
        mf_chart=mf_chart,
        mf_split=mf_split,
        mf_split_chart=mf_split_chart,
        liquid_chart=liq_chart,
        ef_chart=ef_chart,
        metals_chart=metals_chart,
        risk_chart=risk_chart,
        mutual_funds=mf_list,
        retirement=ret_list,
        liquid=liq_list,
        emergency_fund=data.get("emergency_fund", []),
        emergency_fund_by_type=ef_bt,
        metals=met_list,
        risk_rows=risk_rows,
        risk_summary=risk_summary,
    )
