"""
Economic (Look-Through) Asset Allocation
=========================================
Answers "what do I actually own economically?" instead of "which product
wrapper is it in?" — maps every holding (mutual fund, retirement account,
liquid/emergency-fund instrument, metal) to its underlying exposure across
six standard buckets:

    Equity, Corporate Debt, Government Securities, Cash, Gold, Other

Rules
-----
  - Insurance is excluded (matches the net-worth exclusion in
    calculation_engine — insurance is not an investable asset).
  - A holding's mix comes from, in priority order:
      1. An explicit ``LookThrough`` sheet row keyed by the fund Identifier
         (mutual funds) or the instrument Type (retirement/liquid/emergency
         fund/metals) — the investor's own declared look-through.
      2. A conservative, clearly-labelled built-in default for well-known
         product types (see ``_DEFAULT_MIX``).
      3. "Other" (Unclassified) — used whenever neither of the above
         applies. We deliberately do NOT guess a scheme's underlying mix
         (e.g. NPS E/C/G split) without the investor supplying it.
  - The equity sleeve can optionally be broken into Large/Mid/Small/
    International style buckets, again only from an explicit override —
    otherwise it is reported as "Unclassified" style.

Public API
----------
build_economic_allocation(data: dict, portfolio) -> dict
"""

from typing import Any, Dict, List, Optional


_BUCKETS = [
    ("equity", "Equity", "#4f8ef7"),
    ("corporate_debt", "Corporate Debt", "#9333ea"),
    ("govt_securities", "Government Securities", "#14b8a6"),
    ("cash", "Cash", "#22c55e"),
    ("gold", "Gold", "#e8b44a"),
    ("other", "Other", "#94a3b8"),
]

_STYLE_BUCKETS = [
    ("equity_large", "Large Cap"),
    ("equity_mid", "Mid Cap"),
    ("equity_small", "Small Cap"),
    ("equity_intl", "International"),
]

# Conservative, clearly-labelled defaults. Every entry here is a documented
# market assumption, not a fabricated precision figure — investors can
# always override via the LookThrough sheet.
_DEFAULT_MIX: Dict[str, Dict[str, float]] = {
    "EQUITY_FUND":    {"equity": 100.0},
    "DEBT_FUND":      {"corporate_debt": 100.0},
    "GILT_FUND":      {"govt_securities": 100.0},
    "HYBRID_FUND":    {"equity": 60.0, "corporate_debt": 40.0},
    "ARBITRAGE_FUND": {"equity": 20.0, "cash": 80.0},
    "CASH_LIKE":      {"cash": 100.0},
    # EPFO's published asset mix is ~85% debt (dominated by G-Sec/SDL) and
    # up to 15% equity via index ETFs. Approximated here; override via
    # LookThrough keyed "PF" / "EPF" for a precise split.
    "EPF":            {"govt_securities": 85.0, "equity": 15.0},
    "PPF":            {"govt_securities": 100.0},
    "GOLD_LIKE":      {"gold": 100.0},
}


def _pct(part: float, total: float) -> float:
    return round((part / total) * 100, 1) if total > 0 else 0.0


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _normalize_mix(raw: Dict[str, float]) -> Optional[Dict[str, float]]:
    """Scale a bucket-pct dict so it sums to 100. None if it's empty/zero."""
    total = sum(v for v in raw.values() if v > 0)
    if total <= 0:
        return None
    return {k: (v / total) * 100.0 for k, v in raw.items() if v > 0}


def _override_mix(override: dict) -> Optional[Dict[str, float]]:
    raw = {
        "equity": _safe_float(override.get("equity")),
        "corporate_debt": _safe_float(override.get("corporate_debt")),
        "govt_securities": _safe_float(override.get("govt_securities")),
        "cash": _safe_float(override.get("cash")),
        "gold": _safe_float(override.get("gold")),
        "other": _safe_float(override.get("other")),
    }
    return _normalize_mix(raw)


def _override_style(override: dict) -> Optional[Dict[str, float]]:
    raw = {
        "equity_large": _safe_float(override.get("equity_large")),
        "equity_mid": _safe_float(override.get("equity_mid")),
        "equity_small": _safe_float(override.get("equity_small")),
        "equity_intl": _safe_float(override.get("equity_intl")),
    }
    return _normalize_mix(raw)


def _classify_mf_category(fund: dict) -> str:
    name = str(fund.get("fund_name", "")).lower()
    fund_type = str(fund.get("fund_type", "")).lower()
    haystack = f"{name} {fund_type}"

    if any(k in haystack for k in ("gilt", "g-sec", "gsec", "government securities")):
        return "GILT_FUND"
    if "arbitrage" in haystack:
        return "ARBITRAGE_FUND"
    if any(k in haystack for k in ("hybrid", "balanced", "asset allocation", "multi asset", "dynamic asset", "conservative", "aggressive")):
        return "HYBRID_FUND"
    if any(k in haystack for k in ("debt", "bond", "income", "liquid", "money market", "corporate", "short duration", "ultra short", "credit risk")):
        return "DEBT_FUND"
    return "EQUITY_FUND"


def _classify_instrument_category(type_label: str) -> Optional[str]:
    t = (type_label or "").strip().lower()
    if t in ("pf", "epf"):
        return "EPF"
    if "ppf" in t:
        return "PPF"
    if t in ("savings", "cash", "current", "fd", "rd", "bank"):
        return "CASH_LIKE"
    if t in ("gold", "silver"):
        return "GOLD_LIKE"
    return None  # NPS and anything else: no safe default, must be overridden


def _resolve_mix(key: str, category: Optional[str], overrides: Dict[str, dict]) -> tuple:
    """Return (mix_dict, style_dict_or_None, source) for one holding."""
    override = overrides.get(key.strip().upper()) if key else None
    if override is not None:
        mix = _override_mix(override)
        if mix is not None:
            return mix, _override_style(override), "override"

    if category and category in _DEFAULT_MIX:
        return dict(_DEFAULT_MIX[category]), None, "default"

    return {"other": 100.0}, None, "unclassified"


def _contribute(
    bucket_totals: Dict[str, float],
    bucket_contributors: Dict[str, List[dict]],
    equity_style_totals: Dict[str, float],
    label: str,
    value: float,
    mix: Dict[str, float],
    style: Optional[Dict[str, float]],
    source: str,
) -> None:
    for bucket_key, pct in mix.items():
        amount = value * (pct / 100.0)
        if amount <= 0:
            continue
        bucket_totals[bucket_key] = bucket_totals.get(bucket_key, 0.0) + amount
        bucket_contributors.setdefault(bucket_key, []).append({
            "label": label,
            "value": amount,
            "mix_pct": round(pct, 1),
            "source": source,
        })
        if bucket_key == "equity":
            if style:
                for style_key, style_pct in style.items():
                    equity_style_totals[style_key] = equity_style_totals.get(style_key, 0.0) + amount * (style_pct / 100.0)
            else:
                equity_style_totals["unclassified"] = equity_style_totals.get("unclassified", 0.0) + amount


def build_economic_allocation(data: Dict[str, Any], portfolio: Any) -> dict:
    overrides = {
        str(o.get("key", "")).strip().upper(): o
        for o in (data.get("lookthrough_overrides") or [])
        if o.get("key")
    }
    targets = {
        str(k).strip().lower(): _safe_float(v)
        for k, v in (data.get("targets") or {}).items()
    }

    bucket_totals: Dict[str, float] = {key: 0.0 for key, _, _ in _BUCKETS}
    bucket_contributors: Dict[str, List[dict]] = {}
    equity_style_totals: Dict[str, float] = {}
    unclassified_notes: List[str] = []

    for fund in getattr(portfolio, "mutual_funds", []) or []:
        value = _safe_float(fund.get("current_value", 0))
        if value <= 0:
            continue
        identifier = str(fund.get("identifier", ""))
        category = _classify_mf_category(fund)
        mix, style, source = _resolve_mix(identifier, category, overrides)
        _contribute(bucket_totals, bucket_contributors, equity_style_totals,
                    str(fund.get("fund_name", "Fund")), value, mix, style, source)

    for item in getattr(portfolio, "retirement", []) or []:
        value = _safe_float(item.get("amount", 0))
        if value <= 0:
            continue
        type_label = str(item.get("type", ""))
        category = _classify_instrument_category(type_label)
        mix, style, source = _resolve_mix(type_label, category, overrides)
        if source == "unclassified":
            unclassified_notes.append(
                f"{type_label or 'Retirement instrument'} (₹{value:,.0f}) has no declared look-through mix — "
                f"add a LookThrough row keyed \"{type_label}\" to classify it."
            )
        _contribute(bucket_totals, bucket_contributors, equity_style_totals,
                    type_label or "Retirement", value, mix, style, source)

    for item in (getattr(portfolio, "liquid", []) or []) + (getattr(portfolio, "emergency_fund", []) or []):
        value = _safe_float(item.get("amount", 0))
        if value <= 0:
            continue
        type_label = str(item.get("type", ""))
        category = _classify_instrument_category(type_label)
        mix, style, source = _resolve_mix(type_label, category, overrides)
        label = str(item.get("account_name") or type_label or "Account")
        _contribute(bucket_totals, bucket_contributors, equity_style_totals,
                    label, value, mix, style, source)

    for item in getattr(portfolio, "metals", []) or []:
        value = _safe_float(item.get("value", 0))
        if value <= 0:
            continue
        type_label = str(item.get("type", ""))
        category = _classify_instrument_category(type_label)
        mix, style, source = _resolve_mix(type_label, category, overrides)
        _contribute(bucket_totals, bucket_contributors, equity_style_totals,
                    type_label or "Metal", value, mix, style, source)

    basis_total = _safe_float(getattr(portfolio, "net_worth", 0))

    buckets = []
    chart_labels, chart_values, chart_colours = [], [], []
    for key, label, colour in _BUCKETS:
        value = bucket_totals.get(key, 0.0)
        pct = _pct(value, basis_total)
        target = targets.get(label.strip().lower())
        deviation = round(pct - target, 1) if target is not None else None
        contributors = sorted(bucket_contributors.get(key, []), key=lambda c: c["value"], reverse=True)
        buckets.append({
            "key": key,
            "label": label,
            "value": value,
            "pct": pct,
            "target_pct": target,
            "deviation_pct": deviation,
            "contributors": contributors,
        })
        if value > 0:
            chart_labels.append(label)
            chart_values.append(value)
            chart_colours.append(colour)

    equity_style = []
    for key, label in _STYLE_BUCKETS:
        value = equity_style_totals.get(key, 0.0)
        if value > 0:
            equity_style.append({"key": key, "label": label, "value": value, "pct": _pct(value, bucket_totals.get("equity", 0.0))})
    unclassified_style_value = equity_style_totals.get("unclassified", 0.0)
    if unclassified_style_value > 0:
        equity_style.append({
            "key": "unclassified",
            "label": "Unclassified",
            "value": unclassified_style_value,
            "pct": _pct(unclassified_style_value, bucket_totals.get("equity", 0.0)),
        })

    effective_equity_value = bucket_totals.get("equity", 0.0)
    effective_equity_pct = _pct(effective_equity_value, basis_total)

    naive_equity_value = 0.0
    for split in getattr(portfolio, "mf_split", []) or []:
        if split.get("type") == "Equity":
            naive_equity_value = _safe_float(split.get("value", 0))
            break
    naive_equity_pct = _pct(naive_equity_value, basis_total)

    return {
        "basis_total": basis_total,
        "buckets": buckets,
        "chart": {"labels": chart_labels, "values": chart_values, "colours": chart_colours},
        "equity_style": equity_style,
        "effective_equity_value": effective_equity_value,
        "effective_equity_pct": effective_equity_pct,
        "naive_equity_value": naive_equity_value,
        "naive_equity_pct": naive_equity_pct,
        "hidden_equity_delta_pct": round(effective_equity_pct - naive_equity_pct, 1),
        "unclassified_value": bucket_totals.get("other", 0.0),
        "unclassified_pct": _pct(bucket_totals.get("other", 0.0), basis_total),
        "unclassified_notes": unclassified_notes,
        "has_overrides": bool(overrides),
        "has_targets": bool(targets),
    }
