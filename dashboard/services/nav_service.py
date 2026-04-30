"""
NAV Service
===========
Fetches Mutual Fund NAV from AMFI (Association of Mutual Funds in India).

Primary source: https://www.amfiindia.com/spages/NAVAll.txt
  - Tab/semicolon-delimited flat file updated daily.
  - Fields: SchemeCode;ISIN1;ISIN2;SchemeName;NAV;Date

Matching priority: ISIN (col 1 or 2) > Scheme Code (col 0)

Fallback: MFAPI (https://api.mfapi.in/mf/{code}) for any AMFI miss.

Guarantees:
  * get_nav() logs matched scheme name + NAV for audit.
  * Cache is per-identifier, 24-hour TTL.
  * Returns (float, source_str) — never None for price in happy path.
  * When NAV cannot be determined, returns (0.0, error_string).
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache path — Lambda writes only to /tmp; local dev uses project cache/
# ---------------------------------------------------------------------------
def _resolve_cache_path() -> str:
    """
    Return a writable cache path.
    Lambda:    /tmp/cache/nav_cache.json  (always writable)
    Local dev: <project_root>/cache/nav_cache.json
    """
    if os.path.isdir("/tmp"):
        d = "/tmp/cache"
    else:
        _svc = os.path.dirname(os.path.abspath(__file__))
        d = os.path.normpath(os.path.join(_svc, "..", "..", "cache"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "nav_cache.json")


_NAV_CACHE   = _resolve_cache_path()
_AMFI_URL    = "https://www.amfiindia.com/spages/NAVAll.txt"
_MFAPI_URL   = "https://api.mfapi.in/mf/{}"
_CACHE_TTL_H = 24   # hours

# In-memory fallback when file I/O is unavailable
_MEM_CACHE: Dict = {}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; FinanceDashboard/1.0)",
}


# =============================================================================
# CACHE
# =============================================================================

def _now_iso() -> str:
    return datetime.now().isoformat()


def _read_cache() -> Dict:
    try:
        cache_path = _resolve_cache_path()
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning("[NAVService] cache read error: %s — using memory cache", exc)
    return dict(_MEM_CACHE)  # fallback to in-memory


def _write_cache(data: Dict) -> None:
    global _MEM_CACHE
    _MEM_CACHE = dict(data)  # always keep memory copy
    try:
        cache_path = _resolve_cache_path()
        tmp = cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
        os.replace(tmp, cache_path)
    except Exception as exc:
        logger.warning("[NAVService] cache write error: %s — data in memory only", exc)


def _cache_valid(entry: Dict) -> bool:
    """Return True if entry was stored within the last TTL hours."""
    ts = entry.get("timestamp")
    if not ts:
        return False
    try:
        age = datetime.now() - datetime.fromisoformat(ts)
        return age < timedelta(hours=_CACHE_TTL_H)
    except Exception:
        return False


# =============================================================================
# VALIDATION
# =============================================================================

def _validate_nav(nav: float) -> bool:
    """NAV must be positive and below 10 000."""
    ok = 0 < nav < 10_000
    if not ok:
        logger.warning("[NAVService] NAV %.4f failed validation (must be 0 < nav < 10000)", nav)
    return ok


# =============================================================================
# AMFI NAVAll.txt PARSER
# =============================================================================

def _parse_amfi_text(text: str) -> Dict[str, Dict]:
    """
    Parse NAVAll.txt into a lookup dict keyed by both ISINs and Scheme Code.

    File format (semicolon-separated):
      SchemeCode;ISINDivPayout;ISINDivReinvest;SchemeName;NAV;Date

    Returns:
      {
        "<ISIN_or_code>": {
          "scheme_code": str,
          "scheme_name": str,
          "nav":         float,
          "date":        str,
        },
        ...
      }
    """
    index: Dict[str, Dict] = {}

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("Scheme") or ";" not in line:
            continue
        parts = line.split(";")
        if len(parts) < 6:
            continue
        scheme_code = parts[0].strip()
        isin1       = parts[1].strip()
        isin2       = parts[2].strip()
        scheme_name = parts[3].strip()
        nav_raw     = parts[4].strip()
        nav_date    = parts[5].strip()

        try:
            nav = float(nav_raw)
        except ValueError:
            continue

        if not _validate_nav(nav):
            continue

        record = {
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "nav":         nav,
            "date":        nav_date,
        }

        for key in [isin1, isin2, scheme_code]:
            if key and key not in ("-", "N/A", ""):
                index[key.upper()] = record

    logger.info("[NAVService] parsed %d NAV records from AMFI text", len(index))
    return index


def _fetch_amfi_index() -> Optional[Dict[str, Dict]]:
    """Download NAVAll.txt and return parsed index, or None on failure."""
    try:
        import requests as req
        resp = req.get(_AMFI_URL, headers=_HEADERS, timeout=3)
        resp.raise_for_status()
        # AMFI file is latin-1 encoded
        text = resp.content.decode("latin-1")
        idx  = _parse_amfi_text(text)
        if idx:
            return idx
        logger.warning("[NAVService] AMFI response parsed but yielded 0 records")
    except Exception as exc:
        logger.warning("[NAVService] AMFI fetch failed: %s", exc)
    return None


# =============================================================================
# MFAPI FALLBACK
# =============================================================================

def _fetch_mfapi(code: str) -> Optional[Tuple[float, str, str]]:
    """
    Fallback: fetch NAV from MFAPI using numeric scheme code.
    Returns (nav, date, scheme_name) or None.
    """
    # Only attempt with numeric codes
    if not re.fullmatch(r"\d+", code.strip()):
        return None
    try:
        import requests as req
        resp = req.get(_MFAPI_URL.format(code.strip()), headers=_HEADERS, timeout=3)
        if resp.status_code != 200:
            return None
        data = resp.json()
        records = data.get("data", [])
        if not records:
            return None
        latest    = records[0]
        nav       = float(latest["nav"])
        nav_date  = latest["date"]
        name      = data.get("meta", {}).get("scheme_name", "unknown")
        if _validate_nav(nav):
            return nav, nav_date, name
    except Exception as exc:
        logger.warning("[NAVService] MFAPI failed for %s: %s", code, exc)
    return None


# =============================================================================
# PUBLIC API
# =============================================================================

_amfi_index: Optional[Dict[str, Dict]] = None
_amfi_loaded_at: Optional[datetime] = None


def _get_amfi_index(force: bool = False) -> Optional[Dict[str, Dict]]:
    """Return in-memory AMFI index, refreshing if stale (>= 24 h)."""
    global _amfi_index, _amfi_loaded_at
    now = datetime.now()
    stale = (
        _amfi_index is None
        or _amfi_loaded_at is None
        or (now - _amfi_loaded_at) >= timedelta(hours=_CACHE_TTL_H)
        or force
    )
    if stale:
        fetched = _fetch_amfi_index()
        if fetched:
            _amfi_index    = fetched
            _amfi_loaded_at = now
    return _amfi_index


def get_nav(identifier: str, fund_name: str = "") -> Tuple[float, str]:
    """
    Return (nav, source_label) for the given fund identifier.

    Identifier may be:
      * ISIN (INF-prefixed 12-char string)
      * AMFI numeric scheme code

    Matching is done against AMFI NAVAll.txt.
    Falls back to MFAPI (numeric codes only), then persisted cache.

    Audit logging: logs matched scheme name and NAV on every successful lookup.

    Returns (0.0, error_string) when no price can be determined.
    """
    key = identifier.strip().upper()
    cache = _read_cache()

    # Layer 1: valid cache entry
    if key in cache:
        entry = cache[key]
        if _cache_valid(entry):
            nav = float(entry["nav"])
            logger.info(
                "[NAVService][cache] %s -> %s NAV=%.4f date=%s",
                key, entry.get("scheme_name", "?"), nav, entry.get("date", "?"),
            )
            return nav, f"Cached ({entry.get('date', '?')})"

    # Layer 2: AMFI index lookup
    amfi = _get_amfi_index()
    if amfi and key in amfi:
        rec  = amfi[key]
        nav  = rec["nav"]
        logger.info(
            "[NAVService][AMFI] %s -> %s NAV=%.4f date=%s",
            key, rec["scheme_name"], nav, rec["date"],
        )
        cache[key] = {"nav": nav, "date": rec["date"],
                      "scheme_name": rec["scheme_name"], "timestamp": _now_iso()}
        _write_cache(cache)
        return nav, f"AMFI ({rec['date']})"

    # Layer 3: MFAPI fallback
    mf = _fetch_mfapi(key)
    if mf:
        nav, nav_date, name = mf
        logger.info(
            "[NAVService][MFAPI] %s -> %s NAV=%.4f date=%s",
            key, name, nav, nav_date,
        )
        cache[key] = {"nav": nav, "date": nav_date, "scheme_name": name, "timestamp": _now_iso()}
        _write_cache(cache)
        return nav, f"MFAPI ({nav_date})"

    # Layer 4: stale cache
    if key in cache:
        entry = cache[key]
        nav   = float(entry.get("nav", 0))
        if nav > 0:
            logger.warning(
                "[NAVService][stale] %s NAV=%.4f from %s",
                key, nav, entry.get("date", "?"),
            )
            return nav, f"Cached-offline ({entry.get('date', '?')})"

    logger.error("[NAVService] no NAV found for identifier=%s fund=%s", key, fund_name)
    return 0.0, "Not Available"


def get_nav_service():
    """
    Compatibility shim for existing excel_parser.py usage.
    Returns a thin adapter so existing call-sites work unchanged.
    """
    return _NAVServiceAdapter()


class _NAVServiceAdapter:
    """Adapter that exposes the old NAVService.get_nav() interface."""

    def get_nav(self, identifier: str, fund_name: str = "") -> Tuple[Optional[float], str]:
        nav, src = get_nav(identifier, fund_name)
        return (nav if nav > 0 else None), src
