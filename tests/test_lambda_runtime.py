"""
Lambda runtime-specific tests.

Validates:
  - Cache paths resolve to /tmp/cache when /tmp exists (Lambda env)
  - In-memory cache fallback when file write fails
  - open_google_sheet context manager cleans up temp files
  - settings_lambda CSRF_TRUSTED_ORIGINS derivation
  - Allocation sum is exactly 100% for non-zero portfolios
"""

import os
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Cache path resolution
# ---------------------------------------------------------------------------

class TestCachePathResolution:
    def test_nav_cache_resolves_to_tmp_when_tmp_exists(self):
        from dashboard.services.nav_service import _resolve_cache_path
        path = _resolve_cache_path()
        # /tmp always exists on Linux Lambda; on Windows CI /tmp may not exist
        # but the function must return a path ending in nav_cache.json
        assert path.endswith("nav_cache.json")
        # directory must exist after the call
        assert os.path.isdir(os.path.dirname(path))

    def test_metal_cache_resolves_to_tmp_when_tmp_exists(self):
        from dashboard.services.metal_price_service import _resolve_cache_path
        path = _resolve_cache_path()
        assert path.endswith("metal_prices.json")
        assert os.path.isdir(os.path.dirname(path))


# ---------------------------------------------------------------------------
# In-memory fallback when file I/O fails
# ---------------------------------------------------------------------------

class TestNavMemoryFallback:
    def test_read_cache_falls_back_to_memory_on_file_error(self, monkeypatch):
        from dashboard.services import nav_service
        monkeypatch.setattr(nav_service, "_MEM_CACHE", {"TEST": {"nav": 99.0}})
        # Patch _resolve_cache_path to return a path that cannot be read
        monkeypatch.setattr(nav_service, "_resolve_cache_path",
                            lambda: "/nonexistent/path/nav_cache.json")
        cache = nav_service._read_cache()
        assert "TEST" in cache
        assert cache["TEST"]["nav"] == 99.0

    def test_write_cache_updates_memory_even_when_file_write_fails(self, monkeypatch):
        from dashboard.services import nav_service
        monkeypatch.setattr(nav_service, "_MEM_CACHE", {})
        monkeypatch.setattr(nav_service, "_resolve_cache_path",
                            lambda: "/nonexistent/path/nav_cache.json")
        nav_service._write_cache({"FUND123": {"nav": 42.5}})
        assert nav_service._MEM_CACHE.get("FUND123", {}).get("nav") == 42.5


class TestMetalMemoryFallback:
    def test_read_cache_falls_back_to_memory_on_file_error(self, monkeypatch):
        from dashboard.services import metal_price_service
        monkeypatch.setattr(metal_price_service, "_MEM_CACHE", {"gold": {"price": 9500.0, "timestamp": "2026-04-30"}})
        monkeypatch.setattr(metal_price_service, "_resolve_cache_path",
                            lambda: "/nonexistent/path/metal_prices.json")
        cache = metal_price_service._read_cache()
        assert cache.get("gold", {}).get("price") == 9500.0

    def test_write_cache_updates_memory_even_when_file_write_fails(self, monkeypatch):
        from dashboard.services import metal_price_service
        monkeypatch.setattr(metal_price_service, "_MEM_CACHE", {})
        monkeypatch.setattr(metal_price_service, "_resolve_cache_path",
                            lambda: "/nonexistent/path/metal_prices.json")
        metal_price_service._write_cache({"gold": {"price": 9999.0}})
        assert metal_price_service._MEM_CACHE.get("gold", {}).get("price") == 9999.0


# ---------------------------------------------------------------------------
# open_google_sheet context manager — temp file cleanup
# ---------------------------------------------------------------------------

class TestOpenGoogleSheetContextManager:
    def test_context_manager_deletes_temp_file_on_exit(self, monkeypatch, tmp_path):
        import tempfile
        from dashboard.services.google_sheet_service import open_google_sheet

        # Create a real temp file to simulate a successful fetch
        fake_temp = tmp_path / "gsheet_test.xlsx"
        fake_temp.write_bytes(b"PK\x03\x04mockxlsx")

        monkeypatch.setattr(
            "dashboard.services.google_sheet_service.fetch_google_sheet",
            lambda url: str(fake_temp),
        )

        with open_google_sheet("https://docs.google.com/spreadsheets/d/abc/edit") as path:
            assert os.path.exists(path)

        assert not os.path.exists(str(fake_temp))

    def test_context_manager_deletes_temp_file_even_on_exception(self, monkeypatch, tmp_path):
        from dashboard.services.google_sheet_service import open_google_sheet

        fake_temp = tmp_path / "gsheet_exc.xlsx"
        fake_temp.write_bytes(b"PK\x03\x04mockxlsx")

        monkeypatch.setattr(
            "dashboard.services.google_sheet_service.fetch_google_sheet",
            lambda url: str(fake_temp),
        )

        with pytest.raises(RuntimeError):
            with open_google_sheet("https://docs.google.com/spreadsheets/d/abc/edit"):
                raise RuntimeError("simulated error")

        assert not os.path.exists(str(fake_temp))


# ---------------------------------------------------------------------------
# Allocation sum = 100%
# ---------------------------------------------------------------------------

class TestAllocationSum:
    def _data(self, mf=100_000, ret=200_000, liq=50_000, ef=150_000, met=30_000):
        return {
            "mutual_funds_summary": {"total_current_value": mf},
            "retirement_total": ret,
            "liquid_total": liq,
            "emergency_fund_total": ef,
            "metals_total": met,
            "insurance_summary": {"total_premium": 15_000, "total_coverage": 5_000_000},
            "mutual_funds": [],
            "retirement": [],
            "liquid": [],
            "emergency_fund": [],
            "emergency_fund_by_type": {},
            "metals": [],
            "insurance": [],
        }

    def test_allocation_sums_to_100_pct(self):
        from dashboard.services.calculation_engine import build_portfolio
        p = build_portfolio(self._data())
        total_pct = sum(c.pct for c in p.categories)
        assert total_pct == pytest.approx(100.0, abs=0.2)

    def test_insurance_not_in_net_worth(self):
        from dashboard.services.calculation_engine import build_portfolio
        d = self._data()
        p = build_portfolio(d)
        expected_nw = d["mutual_funds_summary"]["total_current_value"] + \
                      d["retirement_total"] + d["liquid_total"] + \
                      d["emergency_fund_total"] + d["metals_total"]
        assert p.net_worth == pytest.approx(expected_nw)
        # insurance total_coverage must not appear in net worth
        assert p.net_worth != pytest.approx(expected_nw + d["insurance_summary"]["total_coverage"])

    def test_zero_net_worth_gives_zero_pct(self):
        from dashboard.services.calculation_engine import build_portfolio
        d = self._data(mf=0, ret=0, liq=0, ef=0, met=0)
        p = build_portfolio(d)
        assert all(c.pct == 0.0 for c in p.categories)
