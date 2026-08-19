import io
import os
import zipfile

import pytest

from dashboard.services.google_sheet_service import (
    GoogleSheetAccessError,
    GoogleSheetError,
    InvalidGoogleSheetUrl,
    fetch_google_sheet,
    open_google_sheet,
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


def _xlsx_payload() -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("xl/workbook.xml", "<workbook />")
    return payload.getvalue()


def test_extract_google_sheet_id_from_standard_url():
    url = "https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit#gid=0"
    assert extract_google_sheet_id(url) == "1abcDEF_123-xyz"


def test_extract_google_sheet_id_from_query_param_url():
    url = "https://docs.google.com/spreadsheets/u/0/?id=1abcDEF_123-xyz"
    assert extract_google_sheet_id(url) == "1abcDEF_123-xyz"


def test_extract_google_sheet_id_invalid_url_raises():
    with pytest.raises(ValueError):
        extract_google_sheet_id("https://example.com/not-a-sheet")


def test_public_sheet_without_service_account(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", raising=False)
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service.urlopen",
        lambda req, timeout=20: _FakeResponse(_xlsx_payload()),
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
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", raising=False)
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service.urlopen",
        lambda req, timeout=20: _FakeResponse(b"<html>Denied</html>"),
    )
    with pytest.raises(GoogleSheetAccessError):
        fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")


def test_public_fallback_when_private_export_unavailable(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"configured": true}')
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_private",
        lambda sheet_id: (_ for _ in ()).throw(GoogleSheetAccessError("not shared")),
    )
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_public",
        lambda sheet_id: _xlsx_payload(),
    )

    path = fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")
    try:
        assert os.path.exists(path)
    finally:
        os.unlink(path)


def test_private_service_account_export(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", '{"configured": true}')
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_private",
        lambda sheet_id: _xlsx_payload(),
    )
    public_called = False

    def fail_public(sheet_id):
        nonlocal public_called
        public_called = True
        raise AssertionError("public export should not be called")

    monkeypatch.setattr("dashboard.services.google_sheet_service._fetch_public", fail_public)
    path = fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")
    try:
        assert os.path.exists(path)
        assert not public_called
    finally:
        os.unlink(path)


def test_non_public_sheet_without_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", raising=False)
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_public",
        lambda sheet_id: (_ for _ in ()).throw(GoogleSheetAccessError("not public")),
    )

    with pytest.raises(GoogleSheetAccessError):
        fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")


def test_malformed_private_credentials_can_fall_back_to_public(monkeypatch):
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", "not-json")
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_private",
        lambda sheet_id: (_ for _ in ()).throw(GoogleSheetError("invalid credentials")),
    )
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_public",
        lambda sheet_id: _xlsx_payload(),
    )

    path = fetch_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit")
    os.unlink(path)


def test_open_google_sheet_removes_temporary_file(monkeypatch):
    temp_path = None
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", raising=False)
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()
    monkeypatch.setattr(
        "dashboard.services.google_sheet_service._fetch_public",
        lambda sheet_id: _xlsx_payload(),
    )

    with open_google_sheet("https://docs.google.com/spreadsheets/d/1abcDEF_123-xyz/edit") as path:
        temp_path = path
        assert os.path.exists(path)

    assert temp_path is not None
    assert not os.path.exists(temp_path)


def test_service_account_can_load_from_secrets_manager(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_SECRET_ID", "finance-dash/google-service-account")
    monkeypatch.setenv("AWS_REGION", "ap-south-1")
    from dashboard.services import google_sheet_service
    google_sheet_service._load_service_account_json.cache_clear()

    class FakeSecretsClient:
        def get_secret_value(self, SecretId):
            assert SecretId == "finance-dash/google-service-account"
            return {"SecretString": '{"type": "service_account"}'}

    monkeypatch.setattr("boto3.client", lambda *args, **kwargs: FakeSecretsClient())
    assert google_sheet_service._load_service_account_json() == '{"type": "service_account"}'
    google_sheet_service._load_service_account_json.cache_clear()
