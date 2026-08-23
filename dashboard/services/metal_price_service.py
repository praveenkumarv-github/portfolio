"""
Metal Price Service
===================
Fetches Gold and Silver prices per gram in INR from GoodReturns (Chennai page).

Fallback chain:
  1. Live scrape  - GoodReturns via BeautifulSoup (resilient multi-strategy)
  2. Local cache  - data/metal_prices.json (any age)
  3. Safe default - hard-coded 2026 approximate prices with warning

Guarantees:
  * get_metal_price() NEVER returns None, NEVER raises
  * Prices validated: gold > 1000, silver > 10 before acceptance
  * Cache writes are atomic (tmp -> rename)
"""

import json
import logging
import os
import re
from datetime import date
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Cache path — Lambda writes only to /tmp; local dev uses project data/
# ---------------------------------------------------------------------------
def _resolve_cache_path() -> str:
    """
    Return a writable cache path.
    Lambda:    /tmp/cache/metal_prices.json
    Local dev: <project_root>/data/metal_prices.json
    """
    if os.path.isdir("/tmp"):
        d = "/tmp/cache"
    else:
        _svc = os.path.dirname(os.path.abspath(__file__))
        d = os.path.normpath(os.path.join(_svc, "..", "..", "data"))
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "metal_prices.json")


CACHE_FILE = _resolve_cache_path()   # kept for backward-compat with tests
CACHE_DIR  = os.path.dirname(CACHE_FILE)

# In-memory fallback when file I/O is unavailable
_MEM_CACHE: Dict = {}

# Sanity bounds (INR/gram)
_BOUNDS = {
    "gold"  : (1_000.0, 200_000.0),
    "silver": (    10.0,   5_000.0),
}

# Safe defaults (approx Apr 2026 India spot)
_SAFE_DEFAULTS = {
    "gold"  : 9_200.0,
    "silver": 110.0,
}

_GOLD_URL   = "https://www.goodreturns.in/gold-rates/chennai.html"
_SILVER_URL = "https://www.goodreturns.in/silver-rates/chennai.html"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}


# =============================================================================
# CACHE
# =============================================================================

def _today() -> str:
    return date.today().isoformat()


def _read_cache() -> Dict:
    try:
        cache_path = _resolve_cache_path()
        if os.path.exists(cache_path):
            with open(cache_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        logger.warning("[MetalPrice] cache read error: %s — using memory cache", exc)
    return dict(_MEM_CACHE)


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
        logger.warning("[MetalPrice] cache write error: %s — data in memory only", exc)


def _is_fresh(entry: Dict) -> bool:
    """Return True if entry was written today."""
    return isinstance(entry, dict) and entry.get("timestamp") == _today()


# =============================================================================
# VALIDATION
# =============================================================================

def _validate(metal: str, price: float) -> bool:
    """Return True if price is within sanity bounds."""
    lo, hi = _BOUNDS.get(metal, (0.0, float("inf")))
    ok = lo < price < hi
    if not ok:
        logger.warning(
            "[MetalPrice] %s price %.2f outside bounds [%.0f, %.0f]",
            metal, price, lo, hi,
        )
    return ok


# =============================================================================
# LIVE SCRAPER
# =============================================================================

def _extract_1gram_price(soup, metal: str) -> Optional[float]:
    """
    Multi-strategy extractor for 1-gram price from a GoodReturns page.

    Strategy A: tag containing literal "1 gram" text -> adjacent price cell.
    Strategy B: CSS selectors for known GoodReturns table classes.
    Strategy C: regex over full page text as last resort.
    """
    # Strategy A ---------------------------------------------------------
    # Find cells containing "1 gram" then look at the immediate next-sibling
    # cell WITHIN THE SAME ROW only (avoids false positives from adjacent rows).
    for tag in soup.find_all(string=re.compile(r"1\s*[Gg]ram", re.I)):
        cell = tag.parent  # the <td> or <span> holding "1 gram"
        row  = cell.parent if cell else None
        if row is None:
            continue
        # Search only the other cells in the same row
        for sibling in row.find_all(["td", "th"]):
            txt = sibling.get_text(" ", strip=True)
            if re.search(r"1\s*[Gg]ram", txt, re.I):
                continue  # skip the "1 gram" cell itself
            m = re.search(r"[\u20b9Rs.\s]*(\d[\d,]+\.?\d*)", txt)
            if m:
                val = float(m.group(1).replace(",", ""))
                if _validate(metal, val):
                    return val

    # Strategy B ---------------------------------------------------------
    selectors = [
        "table.gold-rate-table tr",
        "table.silver-rate-table tr",
        ".gold_silver_table tr",
        ".rates-table tr",
        "table tr",
    ]
    for sel in selectors:
        for row in soup.select(sel):
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells]
            if any(re.match(r"1\s*[Gg]ram", t) for t in texts):
                for txt in texts:
                    m = re.search(r"(\d[\d,]+\.?\d*)", txt)
                    if m:
                        val = float(m.group(1).replace(",", ""))
                        if _validate(metal, val):
                            return val

    # Strategy C ---------------------------------------------------------
    full = soup.get_text("\n")
    pattern = re.compile(
        r"1\s*[Gg]ram.{0,80}?[\u20b9Rs.\s]+(\d[\d,]+\.?\d*)",
        re.DOTALL,
    )
    for m in pattern.finditer(full):
        val = float(m.group(1).replace(",", ""))
        if _validate(metal, val):
            return val

    # Strategy D — ticker markers used when the "1 gram" row label is absent
    # (current GoodReturns silver page only quotes /kg).
    metal_word = re.escape(metal)
    per_gram = re.search(
        rf"{metal_word}\s*[\u20b9Rs.\s]*([\d,]+(?:\.\d+)?)\s*/\s*(?:gm|g)\b",
        full,
        re.I,
    )
    if per_gram:
        val = float(per_gram.group(1).replace(",", ""))
        if _validate(metal, val):
            return val

    per_kg = re.search(
        rf"{metal_word}\s*[\u20b9Rs.\s]*([\d,]+(?:\.\d+)?)\s*/\s*kg",
        full,
        re.I,
    )
    if per_kg:
        val = float(per_kg.group(1).replace(",", "")) / 1000.0
        if _validate(metal, val):
            return val

    return None


def _scrape(url: str, metal: str) -> Optional[float]:
    """Fetch a GoodReturns page and return the 1g price, or None."""
    try:
        import requests as req
        from bs4 import BeautifulSoup
        resp = req.get(url, headers=_HEADERS, timeout=3)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")
        price = _extract_1gram_price(soup, metal)
        if price:
            logger.info("[MetalPrice] live %s=%.2f from %s", metal, price, url)
        return price
    except Exception as exc:
        logger.warning("[MetalPrice] scrape failed (%s): %s", url, exc)
        return None


def _fetch_live() -> Dict[str, float]:
    """Scrape both metals. Returns dict with only successfully scraped metals."""
    prices: Dict[str, float] = {}
    gold = _scrape(_GOLD_URL, "gold")
    if gold:
        prices["gold"] = gold
    silver = _scrape(_SILVER_URL, "silver")
    if silver:
        prices["silver"] = silver
    return prices


# =============================================================================
# PUBLIC API
# =============================================================================

def get_metal_price(metal_type: str) -> Tuple[float, str]:
    """
    Return (price_per_gram_inr, source_label).

    Fallback order:
      1. Fresh cache entry written today (manual overrides included)
      2. Live scrape -> write cache for all scraped metals
      3. Stale cache entry (any age)
      4. Safe default constant

    Never returns None.  Never raises.
    """
    metal = metal_type.lower().strip()
    cache = _read_cache()
    entry = cache.get(metal, {})

    # Layer 1: fresh cache
    if _is_fresh(entry) and entry.get("price", 0) > 0:
        src = "Manual" if entry.get("manual") else f"Cached ({entry['timestamp']})"
        return float(entry["price"]), src

    # Layer 2: live fetch
    try:
        live = _fetch_live()
    except Exception as exc:
        logger.warning("[MetalPrice] _fetch_live raised: %s", exc)
        live = {}
    if live:
        for m, p in live.items():
            cache[m] = {"price": p, "timestamp": _today(), "source": "live", "manual": False}
        _write_cache(cache)
        if metal in live:
            return float(live[metal]), "Live (GoodReturns)"

    # Layer 3: stale cache
    if entry.get("price", 0) > 0:
        ts  = entry.get("timestamp", "unknown")
        src = "Manual" if entry.get("manual") else f"Cached ({ts})"
        return float(entry["price"]), src

    # Layer 4: safe default
    default = _SAFE_DEFAULTS.get(metal, 0.0)
    logger.error("[MetalPrice] all layers failed for %s — using default %.2f", metal, default)
    return default, "Default (update needed)"


def get_all_metal_prices() -> Dict[str, Tuple[float, str]]:
    """Return prices for all tracked metals."""
    return {
        "gold"  : get_metal_price("gold"),
        "silver": get_metal_price("silver"),
    }


def set_manual_price(metal_type: str, price: float) -> bool:
    """Store a manual price override. Returns True on success."""
    metal = metal_type.lower().strip()
    if not _validate(metal, price):
        return False
    cache = _read_cache()
    cache[metal] = {
        "price": float(price),
        "timestamp": _today(),
        "source": "manual",
        "manual": True,
    }
    _write_cache(cache)
    logger.info("[MetalPrice] manual price set %s=%.2f", metal, price)
    return True


def refresh_prices() -> Dict[str, Tuple[float, str]]:
    """
    Force a fresh live fetch, ignoring any cached values.
    Manual overrides are preserved.
    """
    cache = _read_cache()
    for m in ["gold", "silver"]:
        if not cache.get(m, {}).get("manual"):
            cache.pop(m, None)
    _write_cache(cache)
    return get_all_metal_prices()
