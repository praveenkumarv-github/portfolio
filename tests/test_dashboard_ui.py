import os
import csv
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from dashboard.models import FileUploadHistory
from dashboard.views import dashboard_view


def test_csv_export_neutralizes_formulas_and_quotes_cells():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to exercise the browser CSV serializer")
    template = (Path(__file__).resolve().parents[1] / "dashboard/templates/dashboard/dashboard.html").read_text(encoding="utf-8")
    serializer = "function csvCell(value){" + template.split("function csvCell(value){", 1)[1].split("function exportExcel(){", 1)[0]
    values = ['=1+1', '+1+1', '-1+1', '@SUM(1)', '\t=1+1', '\r=1+1', 'Fund, "A"', '100.25']
    result = subprocess.run(
        [node, "-e", serializer + "console.log(" + json.dumps(values) + ".map(csvCell).join(','));"],
        text=True, capture_output=True, check=True, timeout=10,
    )
    cells = next(csv.reader(io.StringIO(result.stdout)))
    assert cells[:6] == ["'" + value.strip() for value in values[:6]]
    assert cells[6:] == values[6:]


def _build_excel(fund_name: str = "Fund A") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    with pd.ExcelWriter(tmp.name, engine="openpyxl") as w:
        pd.DataFrame([{"FundName": fund_name, "Units": 100.0, "Identifier": "119551"}]).to_excel(w, sheet_name="MutualFunds", index=False)
        pd.DataFrame([{"Type": "EPF", "Amount": 500000}]).to_excel(w, sheet_name="Retirement", index=False)
        pd.DataFrame([{"AccountName": "SBI", "Type": "Savings", "Amount": 120000}]).to_excel(w, sheet_name="Liquid", index=False)
        pd.DataFrame([{"AccountName": "FD", "Type": "FD", "Amount": 200000, "MaturityDate": "2026-12-31"}]).to_excel(w, sheet_name="EmergencyFund", index=False)
        pd.DataFrame([{"Type": "Term", "Provider": "LIC", "Premium": 15000, "Coverage": 10000000}]).to_excel(w, sheet_name="Insurance", index=False)
        pd.DataFrame([{"Type": "Gold", "Quantity": 10.0}, {"Type": "Silver", "Quantity": 100.0}]).to_excel(w, sheet_name="Metals", index=False)
    return tmp.name


@pytest.mark.django_db
class TestDashboardUI:
    def test_dashboard_renders_required_charts_and_blades(self):
        path = _build_excel()
        FileUploadHistory.objects.create(file_path=path)

        try:
            request = RequestFactory().get("/")
            setattr(request, "session", {})
            setattr(request, "_messages", FallbackStorage(request))

            with patch("dashboard.services.excel_parser.get_nav_service") as nav_factory:
                nav_factory.return_value.get_nav.return_value = (50.0, "AMFI (mock)")
                with patch("dashboard.services.excel_parser.get_metal_price") as metal_fn:
                    metal_fn.side_effect = lambda m: (9000.0, "Live") if m.lower() == "gold" else (110.0, "Live")
                    resp = dashboard_view(request)

            body = resp.content.decode("utf-8")
            assert resp.status_code == 200
            assert "id=\"allocChart\"" in body
            assert "Portfolio Distribution" in body
            assert 'class="portfolio-blocks"' in body
            assert "pb-track" in body
            assert "id=\"trendChart\"" in body
            assert "id=\"mfBladeChart\"" in body
            assert "id=\"blade-retirement\"" in body
            assert "id=\"body-blade-retirement\"" in body
            assert "id=\"liqBladeChart\"" in body
            assert "id=\"efBladeChart\"" in body
            assert "id=\"metBladeChart\"" in body
            assert "id=\"riskBladeChart\"" in body
            assert "function toggleBlade" in body
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_workbook_labels_cannot_break_out_of_json_script(self):
        malicious_name = "</script><script>alert('xss')</script>"
        path = _build_excel(malicious_name)
        FileUploadHistory.objects.create(file_path=path)

        try:
            request = RequestFactory().get("/")
            setattr(request, "session", {})
            setattr(request, "_messages", FallbackStorage(request))
            with patch("dashboard.services.excel_parser.get_nav_service") as nav_factory:
                nav_factory.return_value.get_nav.return_value = (50.0, "AMFI (mock)")
                with patch(
                    "dashboard.services.excel_parser.get_metal_price",
                    side_effect=lambda metal: (9000.0, "Live") if metal.lower() == "gold" else (110.0, "Live"),
                ):
                    response = dashboard_view(request)

            body = response.content.decode("utf-8")
            assert malicious_name not in body
            assert "\\u003C/script\\u003E" in body
        finally:
            if os.path.exists(path):
                os.unlink(path)