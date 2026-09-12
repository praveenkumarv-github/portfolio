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
from datetime import date as _date
from typing import Dict, List, Any, Optional

from .xirr import xirr as _xirr
from .capital_gains import classify_holding_periods as _classify_holding_periods


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
    retirement_split: List[dict]
    liquid_chart: dict
    liquid_split: List[dict]
    emergency_fund_split: List[dict]
    ef_chart: dict
    metals_split: List[dict]
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

    # Invested-vs-current analytics for mutual funds (SIP/lump-sum ledger, optional)
    mf_analytics: dict = field(default_factory=dict)

    # Flat, filterable ledger of every PURCHASE transaction with today's
    # mark-to-market value, and the same rolled up per fund.
    mf_purchase_lots: List[dict] = field(default_factory=list)
    mf_purchase_summary: List[dict] = field(default_factory=list)
    mf_purchase_groups: List[dict] = field(default_factory=list)

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


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _non_negative(value: Any) -> float:
    return max(_safe_float(value), 0.0)


def _total_from_rows(rows: List[dict], value_key: str, summary_value: Any) -> float:
    if rows:
        return sum(_non_negative(row.get(value_key, 0)) for row in rows)
    return _non_negative(summary_value)


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


def _annotate_transaction_valuations(fund_txns: List[dict], current_nav: float, as_of: _date) -> List[dict]:
    """Attach a mark-to-market value to each PURCHASE row: what these exact
    units are worth today at the fund's live NAV. This ignores whether some
    of those units were later sold (that net position is already reflected
    in the fund's own Units/current_value) — it answers "what is this one
    purchase worth today", not "what remains of it".
    """
    annotated = []
    for t in fund_txns:
        row = dict(t)
        if t["type"] == "Invested" and current_nav > 0:
            current_value = t["units"] * current_nav
            gain = current_value - t["amount"]
            held_days = (as_of - t["date"]).days
            row["current_value"] = current_value
            row["gain"] = gain
            row["gain_pct"] = _pct(gain, t["amount"]) if t["amount"] > 0 else None
            row["holding_days"] = held_days
            row["holding_period"] = "Long-Term" if held_days >= 365 else "Short-Term"
        else:
            row["current_value"] = None
            row["gain"] = None
            row["gain_pct"] = None
            row["holding_days"] = None
            row["holding_period"] = None
        annotated.append(row)
    return annotated


def _fund_transaction_analytics(
    identifier: str, txns: List[dict], current_value: float, current_nav: float = 0.0
) -> dict:
    """Invested amount, absolute gain, XIRR, avg. cost, CAGR, and LTCG/STCG
    split for one fund's SIP/lump-sum ledger.

    net_invested is a simple invested-minus-redeemed running balance (not a
    FIFO/LIFO cost-basis reconstruction) — adequate for a gain/XIRR view.
    avg_cost_nav and capital_gains use a proper FIFO lot walk (see
    capital_gains.py) since holding period and cost-per-unit need actual lots.
    """
    fund_txns = sorted(
        (t for t in txns if t.get("identifier") == identifier),
        key=lambda t: t["date"],
    )
    if not fund_txns:
        return {
            "transactions": [],
            "invested_amount": 0.0,
            "redeemed_amount": 0.0,
            "net_invested": 0.0,
            "absolute_gain": 0.0,
            "absolute_return_pct": None,
            "xirr_pct": None,
            "first_investment_date": None,
            "avg_cost_nav": None,
            "cagr_pct": None,
            "capital_gains": None,
        }

    invested = sum(_non_negative(t["amount"]) for t in fund_txns if t["type"] == "Invested")
    redeemed = sum(_non_negative(t["amount"]) for t in fund_txns if t["type"] == "Redeemed")
    net_invested = invested - redeemed

    invested_units = sum(_non_negative(t["units"]) for t in fund_txns if t["type"] == "Invested")
    redeemed_units = sum(_non_negative(t["units"]) for t in fund_txns if t["type"] == "Redeemed")
    net_units_held = invested_units - redeemed_units
    avg_cost_nav = round(net_invested / net_units_held, 4) if net_units_held > 0 else None

    cashflows = [
        (t["date"], -_non_negative(t["amount"]) if t["type"] == "Invested" else _non_negative(t["amount"]))
        for t in fund_txns
    ]
    if current_value > 0:
        cashflows.append((_date.today(), current_value))

    rate = _xirr(cashflows)
    absolute_gain = current_value - net_invested

    days_held = (_date.today() - fund_txns[0]["date"]).days
    cagr_pct = None
    if net_invested > 0 and current_value > 0 and days_held > 0:
        cagr_pct = round((((current_value / net_invested) ** (365.0 / days_held)) - 1) * 100, 2)

    return {
        "transactions": _annotate_transaction_valuations(fund_txns, current_nav, _date.today()),
        "invested_amount": invested,
        "redeemed_amount": redeemed,
        "net_invested": net_invested,
        "absolute_gain": absolute_gain,
        "absolute_return_pct": _pct(absolute_gain, net_invested) if net_invested > 0 else None,
        "xirr_pct": round(rate * 100, 2) if rate is not None else None,
        "first_investment_date": fund_txns[0]["date"],
        "avg_cost_nav": avg_cost_nav,
        "cagr_pct": cagr_pct,
        "capital_gains": _classify_holding_periods(fund_txns, current_nav, _date.today()),
    }


def _portfolio_mf_analytics(mf_list: List[dict], mf_txns: List[dict]) -> dict:
    """Pooled invested-vs-current + XIRR across only the funds that have a
    recorded transaction ledger — NOT the whole mf_total, otherwise funds
    with no ledger would inflate the pooled gain as if free money.

    Assumes mf_list entries have already been updated with per-fund
    analytics (xirr_pct, capital_gains) so the best/worst ranking and
    capital-gains rollup can reuse that work instead of recomputing it.
    """
    tracked_identifiers = {t.get("identifier") for t in mf_txns}
    tracked_current_value = sum(
        _safe_float(f.get("current_value", 0))
        for f in mf_list
        if f.get("identifier") in tracked_identifiers
    )

    cashflows = []
    invested = 0.0
    redeemed = 0.0
    for t in mf_txns:
        amt = _non_negative(t.get("amount", 0))
        if t.get("type") == "Invested":
            cashflows.append((t["date"], -amt))
            invested += amt
        elif t.get("type") == "Redeemed":
            cashflows.append((t["date"], amt))
            redeemed += amt

    if tracked_current_value > 0:
        cashflows.append((_date.today(), tracked_current_value))

    net_invested = invested - redeemed
    rate = _xirr(cashflows) if cashflows else None
    absolute_gain = tracked_current_value - net_invested

    ranked = [f for f in mf_list if f.get("xirr_pct") is not None]
    best_fund = max(ranked, key=lambda f: f["xirr_pct"], default=None)
    worst_fund = min(ranked, key=lambda f: f["xirr_pct"], default=None)

    def _fund_ref(f):
        if not f:
            return None
        return {"fund_name": f.get("fund_name"), "identifier": f.get("identifier"), "xirr_pct": f.get("xirr_pct")}

    cg_keys = (
        "realized_long_term_gain", "realized_short_term_gain",
        "unrealized_long_term_gain", "unrealized_short_term_gain",
    )
    capital_gains = {key: 0.0 for key in cg_keys}
    for f in mf_list:
        cg = f.get("capital_gains")
        if not cg:
            continue
        for key in cg_keys:
            capital_gains[key] += cg.get(key, 0.0)
    for key in cg_keys:
        capital_gains[key] = round(capital_gains[key], 2)

    return {
        "invested_amount": invested,
        "redeemed_amount": redeemed,
        "net_invested": net_invested,
        "tracked_current_value": tracked_current_value,
        "absolute_gain": absolute_gain,
        "absolute_return_pct": _pct(absolute_gain, net_invested) if net_invested > 0 else None,
        "xirr_pct": round(rate * 100, 2) if rate is not None else None,
        "has_transactions": bool(mf_txns),
        "best_fund": _fund_ref(best_fund),
        "worst_fund": _fund_ref(worst_fund),
        "capital_gains": capital_gains,
    }


def _purchase_lot_ledger(mf_list: List[dict]) -> List[dict]:
    """Flatten every fund's PURCHASE transactions (with their mark-to-market
    fields already attached) into one filterable, date-descending list."""
    lots = []
    for f in mf_list:
        for t in f.get("transactions", []):
            if t.get("type") != "Invested":
                continue
            lots.append({
                "fund_name": f.get("fund_name"),
                "identifier": f.get("identifier"),
                "date": t["date"],
                "units": t["units"],
                "purchase_nav": t["nav"],
                "invested_amount": t["amount"],
                "current_nav": _safe_float(f.get("nav", 0)),
                "current_value": t.get("current_value"),
                "gain": t.get("gain"),
                "gain_pct": t.get("gain_pct"),
                "holding_days": t.get("holding_days"),
                "holding_period": t.get("holding_period"),
            })
    lots.sort(key=lambda row: row["date"], reverse=True)
    return lots


def _purchase_summary_by_fund(lots: List[dict]) -> List[dict]:
    """Group the purchase-lot ledger by fund: total units bought, total
    invested, and total mark-to-market value/gain across all purchases."""
    totals: Dict[str, dict] = {}
    for row in lots:
        key = row["identifier"] or row["fund_name"]
        agg = totals.setdefault(key, {
            "fund_name": row["fund_name"],
            "identifier": row["identifier"],
            "units": 0.0,
            "invested_amount": 0.0,
            "current_value": 0.0,
            "purchase_count": 0,
        })
        agg["units"] += row["units"]
        agg["invested_amount"] += row["invested_amount"]
        agg["current_value"] += row["current_value"] or 0.0
        agg["purchase_count"] += 1

    summary = []
    for agg in totals.values():
        gain = agg["current_value"] - agg["invested_amount"]
        agg["gain"] = gain
        agg["gain_pct"] = _pct(gain, agg["invested_amount"]) if agg["invested_amount"] > 0 else None
        summary.append(agg)
    summary.sort(key=lambda a: a["current_value"], reverse=True)
    return summary


def _purchase_lots_grouped(lots: List[dict]) -> List[dict]:
    """Same purchase-lot ledger as _purchase_summary_by_fund, but keeping the
    individual lots nested per fund for a collapsible group-by-fund view."""
    groups: Dict[str, dict] = {}
    for row in lots:
        key = row["identifier"] or row["fund_name"]
        group = groups.setdefault(key, {
            "fund_name": row["fund_name"],
            "identifier": row["identifier"],
            "lots": [],
            "units": 0.0,
            "invested_amount": 0.0,
            "current_value": 0.0,
        })
        group["lots"].append(row)  # lots list is already date-descending
        group["units"] += row["units"]
        group["invested_amount"] += row["invested_amount"]
        group["current_value"] += row["current_value"] or 0.0

    result = []
    for group in groups.values():
        gain = group["current_value"] - group["invested_amount"]
        group["gain"] = gain
        group["gain_pct"] = _pct(gain, group["invested_amount"]) if group["invested_amount"] > 0 else None
        group["purchase_count"] = len(group["lots"])
        result.append(group)
    result.sort(key=lambda g: g["current_value"], reverse=True)
    return result


def _classify_fund_type(fund: dict) -> str:
    """Classify a mutual fund into Equity/Debt/Hybrid using type or name hints."""
    direct = str(fund.get("fund_type", "")).strip().lower()
    if direct:
        if "hybrid" in direct or "balanced" in direct or "arbitrage" in direct:
            return "Hybrid"
        if "debt" in direct or "bond" in direct or "income" in direct:
            return "Debt"
        if "equity" in direct:
            return "Equity"

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

    if any(k in name for k in hybrid_keys):
        return "Hybrid"
    if any(k in name for k in debt_keys):
        return "Debt"
    if any(k in name for k in equity_keys):
        return "Equity"
    return "Hybrid"


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_portfolio(data: dict) -> PortfolioSummary:
    mf_list = [dict(f) for f in (data.get("mutual_funds") or [])]
    ret_list = [dict(item) for item in (data.get("retirement") or [])]
    liq_list = [dict(item) for item in (data.get("liquid") or [])]
    ef_list = [dict(item) for item in (data.get("emergency_fund") or [])]
    met_list = [dict(item) for item in (data.get("metals") or [])]

    for fund in mf_list:
        fund["current_value"] = _non_negative(fund.get("current_value", 0))
    for item in ret_list:
        item["amount"] = _non_negative(item.get("amount", 0))
    for item in liq_list:
        item["amount"] = _non_negative(item.get("amount", 0))
    for item in ef_list:
        item["amount"] = _non_negative(item.get("amount", 0))
    for item in met_list:
        item["value"] = _non_negative(item.get("value", 0))

    mf_total = _total_from_rows(mf_list, "current_value", (data.get("mutual_funds_summary") or {}).get("total_current_value", 0))
    ret_total = _total_from_rows(ret_list, "amount", data.get("retirement_total", 0))
    liq_total = _total_from_rows(liq_list, "amount", data.get("liquid_total", 0))
    ef_total = _total_from_rows(ef_list, "amount", data.get("emergency_fund_total", 0))
    met_total = _total_from_rows(met_list, "value", data.get("metals_total", 0))

    ins_prem = _non_negative((data.get("insurance_summary") or {}).get("total_premium", 0))
    ins_cov = _non_negative((data.get("insurance_summary") or {}).get("total_coverage", 0))

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
    # Pre-calculate mutual fund percentages against mf_total
    for f in mf_list:
        f["pct"] = _pct(_safe_float(f.get("current_value", 0)), mf_total)

    mf_txns_raw = data.get("mf_transactions") or []
    for f in mf_list:
        f.update(_fund_transaction_analytics(
            f.get("identifier", ""), mf_txns_raw,
            _safe_float(f.get("current_value", 0)), _safe_float(f.get("nav", 0)),
        ))
    mf_analytics = _portfolio_mf_analytics(mf_list, mf_txns_raw)
    mf_purchase_lots = _purchase_lot_ledger(mf_list)
    mf_purchase_summary = _purchase_summary_by_fund(mf_purchase_lots)
    mf_purchase_groups = _purchase_lots_grouped(mf_purchase_lots)

    mf_chart = _mini_chart(
        [str(f.get("fund_name", "Fund"))[:20] for f in mf_list],
        [_safe_float(f.get("current_value", 0)) for f in mf_list],
        [f"hsl({(i*47)%360},60%,55%)" for i in range(len(mf_list))],
    )

    mf_split_totals = {"Equity": 0.0, "Debt": 0.0, "Hybrid": 0.0}
    for fund in mf_list:
        bucket = _classify_fund_type(fund)
        mf_split_totals[bucket] += _safe_float(fund.get("current_value", 0))
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

    for item in liq_list:
        item["pct"] = _pct(_safe_float(item.get("amount", 0)), liq_total)

    liquid_type_totals: Dict[str, float] = {}
    for item in liq_list:
        label = str(item.get("type") or "Other")
        liquid_type_totals[label] = liquid_type_totals.get(label, 0.0) + _safe_float(item.get("amount", 0))

    liquid_split = [
        {"type": label, "value": value, "pct": _pct(value, liq_total)}
        for label, value in sorted(liquid_type_totals.items(), key=lambda pair: pair[1], reverse=True)
    ]

    liq_chart = _mini_chart(
        [str(a.get("account_name", "Account")) for a in liq_list],
        [_safe_float(a.get("amount", 0)) for a in liq_list],
        [f"hsl({(i*67+120)%360},55%,50%)" for i in range(len(liq_list))],
    )

    for item in ret_list:
        item["pct"] = _pct(_safe_float(item.get("amount", 0)), ret_total)

    retirement_split = [
        {
            "type": str(item.get("type") or "Other"),
            "value": _safe_float(item.get("amount", 0)),
            "pct": item["pct"],
        }
        for item in sorted(ret_list, key=lambda row: float(row.get("amount", 0)), reverse=True)
        if float(item.get("amount", 0)) > 0
    ]

    ef_bt: Dict[str, float] = {}
    for item in ef_list:
        label = str(item.get("type") or "Other")
        ef_bt[label] = ef_bt.get(label, 0.0) + _safe_float(item.get("amount", 0))
    emergency_fund_split = [
        {"type": str(key or "Other"), "value": _safe_float(value), "pct": _pct(_safe_float(value), ef_total)}
        for key, value in sorted(ef_bt.items(), key=lambda pair: float(pair[1]), reverse=True)
        if _safe_float(value) > 0
    ]

    ef_chart = _mini_chart(
        [str(k) for k in ef_bt.keys()],
        [_safe_float(v) for v in ef_bt.values()],
        ["#f06b6b", "#fb923c", "#fbbf24", "#34d399", "#60a5fa"],
    )

    for item in met_list:
        item["pct"] = _pct(_safe_float(item.get("value", 0)), met_total)

    metals_split = [
        {
            "type": str(item.get("type") or "Metal"),
            "value": _safe_float(item.get("value", 0)),
            "pct": item["pct"],
        }
        for item in sorted(met_list, key=lambda row: float(row.get("value", 0)), reverse=True)
        if float(item.get("value", 0)) > 0
    ]

    metals_chart = _mini_chart(
        [str(m.get("type", "Metal")) for m in met_list],
        [_safe_float(m.get("value", 0)) for m in met_list],
        ["#e8b44a", "#90a8be"],
    )

    # ── Risk / insurance ──────────────────────────────────────────────────
    risk_rows: List[RiskRow] = []
    for pol in (data.get("insurance") or []):
        status, level = _insurance_status(pol)
        risk_rows.append(RiskRow(
            type=pol.get("type", ""),
            provider=pol.get("provider", ""),
            coverage=_non_negative(pol.get("coverage", 0)),
            premium=_non_negative(pol.get("premium", 0)),
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
        retirement_split=retirement_split,
        liquid_chart=liq_chart,
        liquid_split=liquid_split,
        emergency_fund_split=emergency_fund_split,
        ef_chart=ef_chart,
        metals_split=metals_split,
        metals_chart=metals_chart,
        risk_chart=risk_chart,
        mutual_funds=mf_list,
        retirement=ret_list,
        liquid=liq_list,
        emergency_fund=ef_list,
        emergency_fund_by_type=ef_bt,
        metals=met_list,
        risk_rows=risk_rows,
        risk_summary=risk_summary,
        mf_analytics=mf_analytics,
        mf_purchase_lots=mf_purchase_lots,
        mf_purchase_summary=mf_purchase_summary,
        mf_purchase_groups=mf_purchase_groups,
    )
