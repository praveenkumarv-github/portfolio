"""
Dashboard Aggregator
====================
Single orchestration entry-point:
Excel -> excel_parser -> services -> calculation_engine -> aggregator -> view -> UI
"""

import os
from datetime import datetime
from typing import Any, Dict, Optional

from ..models import NetWorthSnapshot
from .alerts import run_alerts
from .calculation_engine import build_portfolio
from .excel_parser import ExcelParserError, parse_excel_file


_PAYLOAD_CACHE: Dict[str, Any] = {
    "file_path": None,
    "mtime": None,
    "payload": None,
}


def _cache_hit(file_path: str, mtime: float) -> bool:
    return (
        _PAYLOAD_CACHE.get("file_path") == file_path
        and _PAYLOAD_CACHE.get("mtime") == mtime
        and _PAYLOAD_CACHE.get("payload") is not None
    )


def _capture_snapshot(portfolio) -> None:
    """Upsert monthly snapshot from the portfolio summary only."""
    try:
        NetWorthSnapshot.objects.update_or_create(
            month=datetime.now().strftime("%Y-%m"),
            defaults={
                "total_net_worth": portfolio.net_worth,
                "mutual_funds": portfolio.mf_total,
                "retirement": portfolio.retirement_total,
                "liquid": portfolio.liquid_total,
                "emergency_fund": portfolio.emergency_fund_total,
                "metals": portfolio.metals_total,
            },
        )
    except Exception:
        pass


def _build_payload(file_path: str) -> Dict[str, Any]:
    result = parse_excel_file(file_path)
    payload: Dict[str, Any] = {
        "portfolio": None,
        "alerts": [],
        "errors": result.get("errors", []),
        "warnings": result.get("warnings", []),
        "snapshots": [],
        "raw_data": result.get("data", {}),
    }

    if not result.get("success"):
        return payload

    data = result["data"]
    portfolio = build_portfolio(data)
    payload["portfolio"] = portfolio
    payload["alerts"] = run_alerts(data, portfolio)

    _capture_snapshot(portfolio)
    payload["snapshots"] = list(
        NetWorthSnapshot.objects.values(
            "month",
            "total_net_worth",
            "mutual_funds",
            "retirement",
            "liquid",
            "emergency_fund",
            "metals",
        ).order_by("month")
    )
    return payload


def build_dashboard_context(file_path: str) -> Dict[str, Any]:
    """Return the full context payload with in-memory file+mtime caching."""
    mtime = os.path.getmtime(file_path)
    if _cache_hit(file_path, mtime):
        return _PAYLOAD_CACHE["payload"]

    payload = _build_payload(file_path)
    _PAYLOAD_CACHE["file_path"] = file_path
    _PAYLOAD_CACHE["mtime"] = mtime
    _PAYLOAD_CACHE["payload"] = payload
    return payload


def clear_dashboard_cache() -> None:
    _PAYLOAD_CACHE["file_path"] = None
    _PAYLOAD_CACHE["mtime"] = None
    _PAYLOAD_CACHE["payload"] = None
