"""
Capital Gains Holding-Period Classification
============================================
FIFO lot-matching of a fund's MFTransactions ledger to split gains into
long-term / short-term buckets using the 365-day test that Indian tax rules
apply to equity-oriented mutual funds (index funds, ELSS, flexi-cap,
arbitrage funds all qualify as equity-oriented).

This module classifies units and gains by holding period only. It does NOT
compute a rupee tax liability — LTCG/STCG rates, the ₹1.25L exemption, and
"specified mutual fund" slab-rate treatment for debt/low-equity hybrid funds
change over time and depend on your total gains across all investments for
the financial year. Verify the actual liability against your CAS/broker
capital-gains statement or a tax advisor before filing.
"""
from datetime import date as _date
from typing import Any, Dict, List, Optional

LONG_TERM_THRESHOLD_DAYS = 365


def classify_holding_periods(
    fund_txns: List[Dict[str, Any]],
    current_nav: float,
    as_of: Optional[_date] = None,
) -> Dict[str, float]:
    """FIFO-match Invested lots against Redeemed rows (already chronologically
    sorted, single fund) and classify realized + unrealized gain by whether
    the holding period at redemption/valuation is >= 365 days.
    """
    as_of = as_of or _date.today()
    lots: List[Dict[str, float]] = []  # FIFO queue: mutated as units are consumed
    realized_lt_gain = 0.0
    realized_st_gain = 0.0
    realized_lt_units = 0.0
    realized_st_units = 0.0

    for txn in fund_txns:
        if txn["type"] == "Invested":
            lots.append({"date": txn["date"], "units": float(txn["units"]), "nav": float(txn["nav"])})
        elif txn["type"] == "Redeemed":
            remaining = float(txn["units"])
            sale_nav = float(txn["nav"])
            sale_date = txn["date"]
            while remaining > 1e-9 and lots:
                lot = lots[0]
                matched = min(lot["units"], remaining)
                held_days = (sale_date - lot["date"]).days
                gain = matched * (sale_nav - lot["nav"])
                if held_days >= LONG_TERM_THRESHOLD_DAYS:
                    realized_lt_gain += gain
                    realized_lt_units += matched
                else:
                    realized_st_gain += gain
                    realized_st_units += matched
                lot["units"] -= matched
                remaining -= matched
                if lot["units"] <= 1e-9:
                    lots.pop(0)
            # A redemption exceeding all recorded purchase lots means the
            # ledger predates the sheet or is incomplete; validators.py
            # already flags unit mismatches, so it is silently ignored here.

    unrealized_lt_gain = 0.0
    unrealized_st_gain = 0.0
    unrealized_lt_units = 0.0
    unrealized_st_units = 0.0
    for lot in lots:
        held_days = (as_of - lot["date"]).days
        gain = lot["units"] * (current_nav - lot["nav"]) if current_nav > 0 else 0.0
        if held_days >= LONG_TERM_THRESHOLD_DAYS:
            unrealized_lt_gain += gain
            unrealized_lt_units += lot["units"]
        else:
            unrealized_st_gain += gain
            unrealized_st_units += lot["units"]

    return {
        "long_term_threshold_days": LONG_TERM_THRESHOLD_DAYS,
        "realized_long_term_gain": round(realized_lt_gain, 2),
        "realized_short_term_gain": round(realized_st_gain, 2),
        "realized_long_term_units": round(realized_lt_units, 4),
        "realized_short_term_units": round(realized_st_units, 4),
        "unrealized_long_term_gain": round(unrealized_lt_gain, 2),
        "unrealized_short_term_gain": round(unrealized_st_gain, 2),
        "unrealized_long_term_units": round(unrealized_lt_units, 4),
        "unrealized_short_term_units": round(unrealized_st_units, 4),
    }
