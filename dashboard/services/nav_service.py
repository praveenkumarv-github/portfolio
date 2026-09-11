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
_AMFI_URLS   = [
    "https://portal.amfiindia.com/spages/NAVAll.txt",
    "https://www.amfiindia.com/spages/NAVAll.txt",
]
_MFAPI_URL   = "https://api.mfapi.in/mf/{}"
_TV_SCAN_URL = "https://scanner.tradingview.com/india/scan"
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

def _validate_nav(nav: float, log_invalid: bool = True) -> bool:
    """NAV must be positive and below 10 000."""
    ok = 0 < nav < 10_000
    if not ok and log_invalid:
        logger.warning("[NAVService] NAV %.4f failed validation (must be 0 < nav < 10000)", nav)
    return ok


def _normalize_identifier(identifier: str) -> str:
    """
    Normalize fund identifiers to improve lookup hit rate.

    Examples:
      * " 120716.0 " -> "120716"
      * "120,716"    -> "120716"
      * "inf209k01vn8" -> "INF209K01VN8"
    """
    raw = str(identifier).strip().replace(",", "")

    # Convert float-like numeric Excel values to canonical integer scheme codes.
    m = re.fullmatch(r"(\d+)\.0+", raw)
    if m:
        return m.group(1)

    if re.fullmatch(r"\d+", raw):
        return raw

    return raw.upper()


def _normalize_symbol(symbol: str) -> str:
    return str(symbol).strip().upper()


# =============================================================================
# AMFI NAVAll.txt PARSER
# =============================================================================

def _parse_amfi_text(text: str) -> Dict[str, Dict]:
    """
    Parse NAVAll.txt into a lookup dict keyed by both ISINs and Scheme Code.

        File format (semicolon-separated):
            Legacy: SchemeCode;ISINDivPayout;ISINDivReinvest;SchemeName;NAV;Date
            Current: SchemeCode;ISIN1;ISIN2;SchemeName;Plan;Option;NAV;Date

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

        # AMFI added Plan/Option columns in newer dumps; NAV and Date stay at tail.
        nav_raw = parts[-2].strip()
        nav_date = parts[-1].strip()

        try:
            nav = float(nav_raw)
        except ValueError:
            continue

        # AMFI dumps can contain rows with non-portfolio values; skip silently.
        if not _validate_nav(nav, log_invalid=False):
            continue

        record = {
            "scheme_code": scheme_code,
            "scheme_name": scheme_name,
            "nav":         nav,
            "date":        nav_date,
        }

        for key in [isin1, isin2, scheme_code]:
            if key and key not in ("-", "N/A", ""):
                index[_normalize_identifier(key)] = record

    logger.info("[NAVService] parsed %d NAV records from AMFI text", len(index))
    return index


def _fetch_amfi_index() -> Optional[Dict[str, Dict]]:
    """Download NAVAll.txt and return parsed index, or None on failure."""
    import requests as req

    for url in _AMFI_URLS:
        try:
            resp = req.get(url, headers=_HEADERS, timeout=5)
            resp.raise_for_status()
            # AMFI file is latin-1 encoded
            text = resp.content.decode("latin-1")
            idx = _parse_amfi_text(text)
            if idx:
                return idx
            logger.warning("[NAVService] AMFI response parsed but yielded 0 records: %s", url)
        except Exception as exc:
            logger.warning("[NAVService] AMFI fetch failed for %s: %s", url, exc)
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
    normalized = _normalize_identifier(code)
    if not re.fullmatch(r"\d+", normalized):
        return None
    try:
        import requests as req
        resp = req.get(_MFAPI_URL.format(normalized), headers=_HEADERS, timeout=3)
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
        logger.warning("[NAVService] MFAPI failed for %s: %s", normalized, exc)
    return None


def _fetch_symbol_nav(symbol: str) -> Optional[Tuple[float, str]]:
    """
    Fallback: fetch NAV using a TradingView mutual-fund symbol.
    Returns (nav, normalized_symbol) or None.
    """
    normalized = _normalize_symbol(symbol)
    if not normalized:
        return None

    payload = {
        "symbols": {"tickers": [normalized], "query": {"types": []}},
        "columns": ["close", "last_price"],
    }

    try:
        import requests as req

        resp = req.post(_TV_SCAN_URL, json=payload, headers=_HEADERS, timeout=5)
        if resp.status_code != 200:
            return None

        data = resp.json()
        rows = data.get("data", [])
        if not rows:
            return None

        values = rows[0].get("d", [])
        for value in values:
            try:
                nav = float(value)
            except (TypeError, ValueError):
                continue
            if _validate_nav(nav):
                return nav, normalized
    except Exception as exc:
        logger.warning("[NAVService] Symbol fallback failed for %s: %s", normalized, exc)

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


def get_nav(identifier: str, fund_name: str = "", symbol: str = "") -> Tuple[float, str]:
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
    key = _normalize_identifier(identifier)
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

    # Layer 4: Symbol fallback
    symbol_key = _normalize_symbol(symbol)
    sym = _fetch_symbol_nav(symbol_key) if symbol_key else None
    if sym:
        nav, used_symbol = sym
        today = datetime.now().strftime("%d-%b-%Y")
        logger.info(
            "[NAVService][SYMBOL] %s -> %s NAV=%.4f symbol=%s",
            key, fund_name or "unknown", nav, used_symbol,
        )
        cache[key] = {
            "nav": nav,
            "date": today,
            "scheme_name": fund_name or used_symbol,
            "timestamp": _now_iso(),
        }
        # Also cache by symbol for repeat lookups using the same symbol.
        cache[used_symbol] = dict(cache[key])
        _write_cache(cache)
        return nav, f"Symbol ({used_symbol})"

    # Layer 5: stale cache
    if key in cache:
        entry = cache[key]
        nav   = float(entry.get("nav", 0))
        if nav > 0:
            logger.warning(
                "[NAVService][stale] %s NAV=%.4f from %s",
                key, nav, entry.get("date", "?"),
            )
            return nav, f"Cached-offline ({entry.get('date', '?')})"

    logger.error(
        "[NAVService] no NAV found for identifier=%s fund=%s symbol=%s",
        key,
        fund_name,
        symbol_key,
    )
    return 0.0, "Not Available"


def get_nav_service():
    """
    Compatibility shim for existing excel_parser.py usage.
    Returns a thin adapter so existing call-sites work unchanged.
    """
    return _NAVServiceAdapter()


class _NAVServiceAdapter:
    """Adapter that exposes the old NAVService.get_nav() interface."""

    def get_nav(self, identifier: str, fund_name: str = "", symbol: str = "") -> Tuple[Optional[float], str]:
        nav, src = get_nav(identifier, fund_name, symbol)
        return (nav if nav > 0 else None), src
