"""
Tests for NAV Service
======================
Covers: AMFI text parsing, ISIN/code matching, validation,
        MFAPI fallback, cache behaviour, error handling.
"""
import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Minimal AMFI NAVAll.txt samples
# ---------------------------------------------------------------------------

_VALID_AMFI_BLOCK = """\
Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
Open Ended Schemes(Debt Scheme - Banking and PSU Fund)

119551;INF179K01VQ8;INF179K01VR6;Kotak Banking and PSU Debt Fund - Regular Plan - Growth;62.1234;30-Apr-2026
119552;INF179K01VS4;INF179K01VT2;Kotak Banking and PSU Debt Fund - Regular Plan - IDCW;25.4567;30-Apr-2026

Open Ended Schemes(Equity Scheme - Sectoral/ Thematic)

120716;INF209K01VN8;INF209K01VO6;UTI Banking and Financial Services Fund - Regular Plan - Growth;135.6789;30-Apr-2026
"""

_INVALID_NAV_BLOCK = """\
119999;INF000K01XX1;INF000K01XX2;Invalid Fund Zero NAV;0.0;30-Apr-2026
119998;INF000K01YY1;INF000K01YY2;Invalid Fund Huge NAV;99999.9;30-Apr-2026
"""


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------

class TestAMFIParser:
    def test_parses_valid_records(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        assert len(idx) >= 6  # 3 records × 2 ISINs + 3 scheme codes

    def test_isin_lookup(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        assert "INF179K01VQ8" in idx
        assert idx["INF179K01VQ8"]["nav"] == pytest.approx(62.1234)

    def test_secondary_isin_lookup(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        assert "INF179K01VR6" in idx

    def test_scheme_code_lookup(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        assert "119551" in idx

    def test_zero_nav_excluded(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_INVALID_NAV_BLOCK)
        assert "INF000K01XX1" not in idx

    def test_huge_nav_excluded(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_INVALID_NAV_BLOCK)
        assert "INF000K01YY1" not in idx

    def test_header_line_skipped(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        # "Scheme Code" header row should not appear as a record
        assert "SCHEME CODE" not in idx

    def test_empty_input(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text("")
        assert idx == {}

    def test_scheme_name_preserved(self):
        from dashboard.services.nav_service import _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        rec = idx["INF179K01VQ8"]
        assert "Kotak" in rec["scheme_name"]
        assert rec["date"] == "30-Apr-2026"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestNAVValidation:
    def test_valid_nav(self):
        from dashboard.services.nav_service import _validate_nav
        assert _validate_nav(62.12) is True

    def test_zero_nav_invalid(self):
        from dashboard.services.nav_service import _validate_nav
        assert _validate_nav(0.0) is False

    def test_negative_nav_invalid(self):
        from dashboard.services.nav_service import _validate_nav
        assert _validate_nav(-1.0) is False

    def test_over_10000_nav_invalid(self):
        from dashboard.services.nav_service import _validate_nav
        assert _validate_nav(10001.0) is False


# ---------------------------------------------------------------------------
# get_nav with mocked AMFI index
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_nav_cache(tmp_path, monkeypatch):
    import dashboard.services.nav_service as svc
    cache_path = tmp_path / "nav_cache.json"
    monkeypatch.setattr(svc, "_NAV_CACHE", str(cache_path))
    monkeypatch.setattr(svc, "_amfi_index", None)
    monkeypatch.setattr(svc, "_amfi_loaded_at", None)
    yield cache_path


class TestGetNAV:
    def test_amfi_hit(self, tmp_nav_cache):
        """Valid ISIN resolved from AMFI index."""
        from dashboard.services.nav_service import get_nav, _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        with patch("dashboard.services.nav_service._get_amfi_index", return_value=idx):
            nav, src = get_nav("INF179K01VQ8")
        assert nav == pytest.approx(62.1234)
        assert "AMFI" in src

    def test_scheme_code_hit(self, tmp_nav_cache):
        from dashboard.services.nav_service import get_nav, _parse_amfi_text
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        with patch("dashboard.services.nav_service._get_amfi_index", return_value=idx):
            nav, src = get_nav("119552")
        assert nav == pytest.approx(25.4567)

    def test_invalid_isin_returns_zero(self, tmp_nav_cache):
        """Unknown identifier returns (0.0, 'Not Available')."""
        from dashboard.services.nav_service import get_nav
        with patch("dashboard.services.nav_service._get_amfi_index", return_value={}):
            with patch("dashboard.services.nav_service._fetch_mfapi", return_value=None):
                nav, src = get_nav("INVALID123456")
        assert nav == 0.0
        assert "Not Available" in src

    def test_fresh_cache_used(self, tmp_nav_cache):
        """Cache hit within TTL should not call AMFI."""
        from dashboard.services.nav_service import get_nav, _write_cache
        _write_cache({
            "INF179K01VQ8": {
                "nav": 63.0,
                "date": "30-Apr-2026",
                "scheme_name": "Kotak Bond",
                "timestamp": datetime.now().isoformat(),
            }
        })
        with patch("dashboard.services.nav_service._get_amfi_index") as mock_amfi:
            nav, src = get_nav("INF179K01VQ8")
        mock_amfi.assert_not_called()
        assert nav == pytest.approx(63.0)
        assert "Cached" in src

    def test_stale_cache_falls_through_to_amfi(self, tmp_nav_cache):
        from dashboard.services.nav_service import get_nav, _write_cache, _parse_amfi_text
        stale_ts = (datetime.now() - timedelta(hours=25)).isoformat()
        _write_cache({
            "INF179K01VQ8": {
                "nav": 60.0,
                "date": "29-Apr-2026",
                "scheme_name": "Kotak Bond",
                "timestamp": stale_ts,
            }
        })
        idx = _parse_amfi_text(_VALID_AMFI_BLOCK)
        with patch("dashboard.services.nav_service._get_amfi_index", return_value=idx):
            nav, src = get_nav("INF179K01VQ8")
        assert nav == pytest.approx(62.1234)
        assert "AMFI" in src

    def test_mfapi_fallback(self, tmp_nav_cache):
        """When AMFI index is empty, fall back to MFAPI."""
        from dashboard.services.nav_service import get_nav
        mfapi_result = (55.678, "30-Apr-2026", "Some Fund")
        with patch("dashboard.services.nav_service._get_amfi_index", return_value={}):
            with patch("dashboard.services.nav_service._fetch_mfapi", return_value=mfapi_result):
                nav, src = get_nav("119551")
        assert nav == pytest.approx(55.678)
        assert "MFAPI" in src

    def test_stale_cache_offline_fallback(self, tmp_nav_cache):
        """When live fails but stale cache exists, return stale."""
        from dashboard.services.nav_service import get_nav, _write_cache
        stale_ts = (datetime.now() - timedelta(hours=30)).isoformat()
        _write_cache({
            "INF179K01VQ8": {
                "nav": 61.0,
                "date": "28-Apr-2026",
                "scheme_name": "Kotak Bond",
                "timestamp": stale_ts,
            }
        })
        with patch("dashboard.services.nav_service._get_amfi_index", return_value=None):
            with patch("dashboard.services.nav_service._fetch_mfapi", return_value=None):
                nav, src = get_nav("INF179K01VQ8")
        assert nav == pytest.approx(61.0)
        assert "offline" in src.lower() or "cached" in src.lower()
