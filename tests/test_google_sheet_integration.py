import io
import os
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory
from django.test import override_settings

from dashboard.models import FileUploadHistory
from dashboard.services.google_sheet_service import (
    GoogleSheetAccessError,
    GoogleSheetError,
    InvalidGoogleSheetUrl,
)
from dashboard.views import load_google_sheet, upload_file


def _build_excel_bytes() -> bytes:
    blob = io.BytesIO()
    with pd.ExcelWriter(blob, engine="openpyxl") as w:
        pd.DataFrame([{"FundName": "Fund A", "Units": 100.0, "Identifier": "119551"}]).to_excel(w, sheet_name="MutualFunds", index=False)
        pd.DataFrame([{"Type": "EPF", "Amount": 500000}]).to_excel(w, sheet_name="Retirement", index=False)
        pd.DataFrame([{"AccountName": "SBI", "Type": "Savings", "Amount": 120000}]).to_excel(w, sheet_name="Liquid", index=False)
        pd.DataFrame([{"AccountName": "FD", "Type": "FD", "Amount": 200000, "MaturityDate": "2026-12-31"}]).to_excel(w, sheet_name="EmergencyFund", index=False)
        pd.DataFrame([{"Type": "Term", "Provider": "LIC", "Premium": 15000, "Coverage": 10000000}]).to_excel(w, sheet_name="Insurance", index=False)
        pd.DataFrame([{"Type": "Gold", "Quantity": 10.0}, {"Type": "Silver", "Quantity": 100.0}]).to_excel(w, sheet_name="Metals", index=False)
    return blob.getvalue()


def _build_excel_file() -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    with open(tmp.name, "wb") as handle:
        handle.write(_build_excel_bytes())
    return tmp.name


@pytest.mark.django_db
class TestGoogleSheetIntegration:
    def test_google_sheet_load_success(self):
        gsheet_path = _build_excel_file()
        try:
            request = RequestFactory().post("/load-google-sheet/", {"sheet_url": "https://docs.google.com/spreadsheets/d/abc123/edit"})
            setattr(request, "session", {})
            setattr(request, "_messages", FallbackStorage(request))
            with patch("dashboard.views.fetch_google_sheet", return_value=gsheet_path):
                resp = load_google_sheet(request)
            assert resp.status_code == 302
            msg_text = [m.message for m in get_messages(request)]
            assert "Google Sheet loaded successfully." in msg_text
            last = FileUploadHistory.objects.first()
            assert last is not None
            assert last.file_path == gsheet_path
        finally:
            if os.path.exists(gsheet_path):
                os.unlink(gsheet_path)

    def test_google_sheet_invalid_url_message(self):
        request = RequestFactory().post("/load-google-sheet/", {"sheet_url": "bad"})
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        with patch("dashboard.views.fetch_google_sheet", side_effect=InvalidGoogleSheetUrl("bad url")):
            resp = load_google_sheet(request)
        assert resp.status_code == 302
        assert "Invalid Google Sheet URL" in [m.message for m in get_messages(request)]

    def test_google_sheet_private_sheet_message(self):
        request = RequestFactory().post("/load-google-sheet/", {"sheet_url": "https://docs.google.com/spreadsheets/d/private/edit"})
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        with patch("dashboard.views.fetch_google_sheet", side_effect=GoogleSheetAccessError("private")):
            resp = load_google_sheet(request)
        assert resp.status_code == 302
        assert "Sheet not publicly accessible" in [m.message for m in get_messages(request)]

    def test_google_sheet_network_failure_message(self):
        request = RequestFactory().post("/load-google-sheet/", {"sheet_url": "https://docs.google.com/spreadsheets/d/fail/edit"})
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        with patch("dashboard.views.fetch_google_sheet", side_effect=GoogleSheetError("network")):
            resp = load_google_sheet(request)
        assert resp.status_code == 302
        assert "Failed to fetch data" in [m.message for m in get_messages(request)]

    def test_excel_upload_still_works(self, tmp_path):
        content = _build_excel_bytes()
        upload = SimpleUploadedFile(
            "portfolio.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        request = RequestFactory().post("/upload/", {"excel_file": upload})
        setattr(request, "session", {})
        setattr(request, "_messages", FallbackStorage(request))
        with override_settings(MEDIA_ROOT=str(tmp_path)):
            resp = upload_file(request)

        assert resp.status_code == 302
        messages = [m.message for m in get_messages(request)]
        assert any("loaded successfully from Local File" in m for m in messages)
        last = FileUploadHistory.objects.first()
        assert last is not None
        assert os.path.exists(last.file_path)

    def test_parsing_identical_for_google_and_excel_sources(self):
        from dashboard.services.aggregator import build_dashboard_context, clear_dashboard_cache

        local_path = _build_excel_file()
        google_path = _build_excel_file()
        try:
            with patch("dashboard.services.excel_parser.get_nav_service") as nav_factory:
                nav_factory.return_value.get_nav.return_value = (50.0, "AMFI (mock)")
                with patch("dashboard.services.excel_parser.get_metal_price") as metal_fn:
                    metal_fn.side_effect = lambda m: (9000.0, "Live") if m.lower() == "gold" else (110.0, "Live")
                    clear_dashboard_cache()
                    excel_payload = build_dashboard_context(local_path)
                    clear_dashboard_cache()
                    gsheet_payload = build_dashboard_context(google_path)

            assert excel_payload["portfolio"].net_worth == pytest.approx(gsheet_payload["portfolio"].net_worth)
            assert excel_payload["portfolio"].allocation_chart["values"] == gsheet_payload["portfolio"].allocation_chart["values"]
        finally:
            if os.path.exists(local_path):
                os.unlink(local_path)
            if os.path.exists(google_path):
                os.unlink(google_path)
