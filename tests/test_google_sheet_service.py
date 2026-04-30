import os

import pytest

from dashboard.services.google_sheet_service import (
    GoogleSheetAccessError,
    InvalidGoogleSheetUrl,
    fetch_google_sheet,
)
from dashboard.services.url_utils import extract_google_sheet_id


class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def test_extract_google_sheet_id_from_standard_url():
    url = "https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit#gid=0"
    assert extract_google_sheet_id(url) == "1abcDEF_123-xyz"


def test_extract_google_sheet_id_from_query_param_url():
    url = "https://docs.google.com/spreadsheets/u/0/?id=1abcDEF_123-xyz"
    assert extract_google_sheet_id(url) == "1abcDEF_123-xyz"


def test_extract_google_sheet_id_invalid_url_raises():
    with pytest.raises(ValueError):
        extract_google_sheet_id("https://example.com/not-a-sheet")


def test_fetch_google_sheet_downloads_temp_xlsx(monkeypatch):
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service.urlopen",
        lambda req, timeout=20: _FakeResponse(b"PK\x03\x04mockxlsx"),
    )

    path = fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")
    try:
        assert os.path.exists(path)
        assert os.path.basename(path).startswith("gsheet_")
        with open(path, "rb") as handle:
            assert handle.read().startswith(b"PK")
    finally:
        if os.path.exists(path):
            os.unlink(path)


def test_fetch_google_sheet_invalid_url_raises():
    with pytest.raises(InvalidGoogleSheetUrl):
        fetch_google_sheet("not-a-url")


def test_fetch_google_sheet_non_xlsx_payload_raises(monkeypatch):
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service.urlopen",
        lambda req, timeout=20: _FakeResponse(b"<html>Denied</html>"),
    )
    with pytest.raises(GoogleSheetAccessError):
        fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")
