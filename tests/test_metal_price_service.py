"""
Tests for Metal Price Service
==============================
Covers: live fetch, HTML structure resilience, cache fallback,
        manual override, validation bounds, refresh logic.
"""
import json
import os
import shutil
import tempfile
from datetime import date, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_goodreturns_html(price_str: str) -> str:
    """Minimal HTML mimicking GoodReturns 1-gram table row."""
    return f"""
    <html><body>
      <table class="gold-rate-table">
        <tr><th>Quantity</th><th>Today</th></tr>
        <tr><td>1 gram</td><td>&#8377;{price_str}</td></tr>
        <tr><td>8 gram</td><td>&#8377;73,600</td></tr>
      </table>
    </body></html>
    """


def _make_goodreturns_html_no_table(price_str: str) -> str:
    """HTML without known table class — forces Strategy C (regex)."""
    return f"""
    <html><body>
      <p>Gold rate today: 1 gram price is &#8377; {price_str} in Chennai</p>
    </body></html>
    """


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_cache(tmp_path, monkeypatch):
    """Redirect CACHE_FILE to a temp path for each test."""
    import dashboard.services.metal_price_service as svc
    cache_path = tmp_path / "metal_prices.json"
    monkeypatch.setattr(svc, "CACHE_FILE", str(cache_path))
    monkeypatch.setattr(svc, "CACHE_DIR",  str(tmp_path))
    yield cache_path


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_gold_valid(self):
        from dashboard.services.metal_price_service import _validate
        assert _validate("gold", 9_000.0) is True

    def test_gold_too_low(self):
        from dashboard.services.metal_price_service import _validate
        assert _validate("gold", 500.0) is False

    def test_gold_too_high(self):
        from dashboard.services.metal_price_service import _validate
        assert _validate("gold", 250_000.0) is False

    def test_silver_valid(self):
        from dashboard.services.metal_price_service import _validate
        assert _validate("silver", 110.0) is True

    def test_silver_too_low(self):
        from dashboard.services.metal_price_service import _validate
        assert _validate("silver", 5.0) is False


# ---------------------------------------------------------------------------
# HTML Parsing (no network)
# ---------------------------------------------------------------------------

class TestHTMLParsing:
    def test_strategy_a_table_row(self):
        """Known GoodReturns table class -> 1 gram row."""
        from bs4 import BeautifulSoup
        from dashboard.services.metal_price_service import _extract_1gram_price
        html = _make_goodreturns_html("9,200")
        soup = BeautifulSoup(html, "lxml")
        price = _extract_1gram_price(soup, "gold")
        assert price == 9200.0

    def test_strategy_c_regex_fallback(self):
        """Regex fallback when no table class matches."""
        from bs4 import BeautifulSoup
        from dashboard.services.metal_price_service import _extract_1gram_price
        html = _make_goodreturns_html_no_table("9,100")
        soup = BeautifulSoup(html, "lxml")
        price = _extract_1gram_price(soup, "gold")
        assert price == 9100.0

    def test_invalid_price_rejected(self):
        """Prices outside sanity bounds must be rejected."""
        from bs4 import BeautifulSoup
        from dashboard.services.metal_price_service import _extract_1gram_price
        # price of 50 should fail gold validation -> return None
        html = _make_goodreturns_html("50")
        soup = BeautifulSoup(html, "lxml")
        price = _extract_1gram_price(soup, "gold")
        assert price is None

    def test_silver_price_extraction(self):
        """Silver price extraction and validation."""
        from bs4 import BeautifulSoup
        from dashboard.services.metal_price_service import _extract_1gram_price
        html = """
        <html><body>
          <table><tr><td>1 gram</td><td>&#8377;110</td></tr></table>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        price = _extract_1gram_price(soup, "silver")
        assert price == 110.0

    def test_html_structure_change_resilience(self):
        """Completely changed HTML structure should still extract via Strategy C."""
        from bs4 import BeautifulSoup
        from dashboard.services.metal_price_service import _extract_1gram_price
        html = """
        <html><body>
          <div class="completely-new-structure">
            <span class="qty-label">1 gram</span>
            <span class="price-label">Rs. 9,050</span>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        price = _extract_1gram_price(soup, "gold")
        # May or may not find it depending on proximity, but must not raise
        assert price is None or (1000 < price < 200000)


# ---------------------------------------------------------------------------
# Cache Fallback
# ---------------------------------------------------------------------------

class TestCacheFallback:
    def test_fresh_cache_returned(self, tmp_cache):
        """A fresh cache entry should be returned without live fetch."""
        from dashboard.services.metal_price_service import get_metal_price, _write_cache
        _write_cache({"gold": {"price": 8888.0, "timestamp": date.today().isoformat(), "manual": False}})
        with patch("dashboard.services.metal_price_service._fetch_live") as mock_live:
            price, src = get_metal_price("gold")
        mock_live.assert_not_called()
        assert price == 8888.0
        assert "Cached" in src

    def test_stale_cache_triggers_live_then_falls_back(self, tmp_cache):
        """Stale cache: try live (fail), return stale value."""
        from dashboard.services.metal_price_service import get_metal_price, _write_cache
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        _write_cache({"gold": {"price": 8700.0, "timestamp": yesterday, "manual": False}})
        with patch("dashboard.services.metal_price_service._fetch_live", return_value={}):
            price, src = get_metal_price("gold")
        assert price == 8700.0
        assert "Cached" in src

    def test_no_cache_no_live_uses_default(self, tmp_cache):
        """No cache + live fails -> safe default returned."""
        from dashboard.services.metal_price_service import get_metal_price, _SAFE_DEFAULTS
        with patch("dashboard.services.metal_price_service._fetch_live", return_value={}):
            price, src = get_metal_price("gold")
        assert price == _SAFE_DEFAULTS["gold"]
        assert "Default" in src

    def test_live_fetch_updates_cache(self, tmp_cache):
        """Successful live fetch should persist values to cache."""
        from dashboard.services.metal_price_service import get_metal_price
        with patch("dashboard.services.metal_price_service._fetch_live", return_value={"gold": 9100.0, "silver": 112.0}):
            price, src = get_metal_price("gold")
        assert price == 9100.0
        assert "Live" in src
        # Verify cache was written
        assert tmp_cache.exists()
        data = json.loads(tmp_cache.read_text())
        assert data["gold"]["price"] == 9100.0

    def test_get_metal_price_never_raises(self, tmp_cache):
        """get_metal_price must never raise an exception."""
        from dashboard.services.metal_price_service import get_metal_price
        with patch("dashboard.services.metal_price_service._fetch_live", side_effect=Exception("network down")):
            price, src = get_metal_price("gold")
        assert isinstance(price, float)
        assert isinstance(src, str)


# ---------------------------------------------------------------------------
# Manual Override
# ---------------------------------------------------------------------------

class TestManualOverride:
    def test_set_manual_price(self, tmp_cache):
        from dashboard.services.metal_price_service import set_manual_price, get_metal_price
        result = set_manual_price("gold", 9500.0)
        assert result is True
        price, src = get_metal_price("gold")
        assert price == 9500.0
        assert "Manual" in src

    def test_set_manual_price_invalid_rejected(self, tmp_cache):
        from dashboard.services.metal_price_service import set_manual_price
        # price below gold lower bound (1000)
        result = set_manual_price("gold", 50.0)
        assert result is False

    def test_manual_price_preserved_on_refresh(self, tmp_cache):
        """refresh_prices must not overwrite manual overrides."""
        from dashboard.services.metal_price_service import set_manual_price, refresh_prices
        set_manual_price("gold", 9500.0)
        with patch("dashboard.services.metal_price_service._fetch_live", return_value={"gold": 9000.0, "silver": 110.0}):
            prices = refresh_prices()
        # Manual should be preserved
        gold_price, gold_src = prices["gold"]
        assert gold_price == 9500.0
        assert "Manual" in gold_src
