"""
Tests for Excel Parser
========================
Covers: sheet validation, column checks, NAV/metal integration,
        net worth calculation, missing/malformed data handling.
"""
import io
import os
import tempfile
from unittest.mock import patch

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers to build in-memory Excel files
# ---------------------------------------------------------------------------

def _build_excel(sheets: dict) -> str:
    """Write dict of {sheet_name: DataFrame} to a temp .xlsx, return path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.close()
    with pd.ExcelWriter(tmp.name, engine="openpyxl") as w:
        for name, df in sheets.items():
            df.to_excel(w, sheet_name=name, index=False)
    return tmp.name


def _minimal_sheets(
    mf_rows=None,
    retirement_rows=None,
    liquid_rows=None,
    ef_rows=None,
    ins_rows=None,
    metals_rows=None,
):
    """Return a complete minimal set of sheets."""
    if mf_rows is None:
        mf_rows = [{"FundName": "Fund A", "Units": 100.0, "Identifier": "119551"}]
    if retirement_rows is None:
        retirement_rows = [{"Type": "EPF", "Amount": 500000}]
    if liquid_rows is None:
        liquid_rows = [{"AccountName": "SBI Savings", "Type": "Savings", "Amount": 100000}]
    if ef_rows is None:
        ef_rows = [{"AccountName": "FD-1", "Type": "FD", "Amount": 200000, "MaturityDate": "2026-12-31"}]
    if ins_rows is None:
        ins_rows = [{"Type": "Term", "Provider": "LIC", "Premium": 15000, "Coverage": 10000000}]
    if metals_rows is None:
        metals_rows = [{"Type": "Gold", "Quantity": 10.0}, {"Type": "Silver", "Quantity": 100.0}]

    return {
        "MutualFunds":   pd.DataFrame(mf_rows),
        "Retirement":    pd.DataFrame(retirement_rows),
        "Liquid":        pd.DataFrame(liquid_rows),
        "EmergencyFund": pd.DataFrame(ef_rows),
        "Insurance":     pd.DataFrame(ins_rows),
        "Metals":        pd.DataFrame(metals_rows),
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_nav():
    """Patch nav_service to return deterministic NAV=50."""
    with patch(
        "dashboard.services.excel_parser.get_nav_service"
    ) as mock_factory:
        adapter = mock_factory.return_value
        adapter.get_nav.return_value = (50.0, "AMFI (mock)")
        yield adapter


@pytest.fixture()
def mock_metal():
    """Patch metal price service to return deterministic prices."""
    with patch(
        "dashboard.services.excel_parser.get_metal_price"
    ) as mock_fn:
        def side_effect(metal_type):
            if metal_type.lower() == "gold":
                return (9000.0, "Live (mock)")
            return (110.0, "Live (mock)")
        mock_fn.side_effect = side_effect
        yield mock_fn


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestExcelParserHappyPath:
    def test_full_parse_success(self, mock_nav, mock_metal):
        path = _build_excel(_minimal_sheets())
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            assert result["success"] is True
            data = result["data"]
            assert len(data["mutual_funds"]) == 1
            assert len(data["retirement"]) == 1
            assert len(data["liquid"]) == 1
            assert len(data["emergency_fund"]) == 1
            assert len(data["metals"]) == 2
        finally:
            os.unlink(path)

    def test_mutual_fund_nav_calculation(self, mock_nav, mock_metal):
        """Units × NAV = current_value."""
        rows = [{"FundName": "Fund A", "Units": 200.0, "Identifier": "119551"}]
        path = _build_excel(_minimal_sheets(mf_rows=rows))
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            fund = result["data"]["mutual_funds"][0]
            assert fund["units"] == 200.0
            assert fund["nav"] == pytest.approx(50.0)
            assert fund["current_value"] == pytest.approx(10_000.0)
        finally:
            os.unlink(path)

    def test_metals_value_calculation(self, mock_nav, mock_metal):
        """Quantity × price_per_gram = value."""
        rows = [{"Type": "Gold", "Quantity": 50.0}]
        path = _build_excel(_minimal_sheets(metals_rows=rows))
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            metal = result["data"]["metals"][0]
            assert metal["quantity"] == 50.0
            assert metal["price_per_gram"] == pytest.approx(9000.0)
            assert metal["value"] == pytest.approx(450_000.0)
        finally:
            os.unlink(path)

    def test_net_worth_calculation(self, mock_nav, mock_metal):
        """Net worth = MF + Retirement + Liquid + EF + Metals."""
        path = _build_excel(_minimal_sheets())
        try:
            from dashboard.services.excel_parser import parse_excel_file
            from dashboard.services.calculation_engine import build_portfolio
            result = parse_excel_file(path)
            data = result["data"]
            expected_nw = (
                data["mutual_funds_summary"]["total_current_value"]
                + data["retirement_total"]
                + data["liquid_total"]
                + data["emergency_fund_total"]
                + data["metals_total"]
            )
            actual_nw = build_portfolio(data).net_worth
            assert actual_nw == pytest.approx(expected_nw)
        finally:
            os.unlink(path)

    def test_emergency_fund_by_type(self, mock_nav, mock_metal):
        rows = [
            {"AccountName": "FD-1", "Type": "FD",  "Amount": 200000, "MaturityDate": "2026-12-31"},
            {"AccountName": "FD-2", "Type": "FD",  "Amount": 100000, "MaturityDate": "2027-03-31"},
            {"AccountName": "SB-1", "Type": "SB",  "Amount":  50000, "MaturityDate": ""},
        ]
        path = _build_excel(_minimal_sheets(ef_rows=rows))
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            by_type = result["data"]["emergency_fund_by_type"]
            assert by_type.get("FD", 0) == pytest.approx(300_000.0)
            assert by_type.get("SB", 0) == pytest.approx(50_000.0)
        finally:
            os.unlink(path)

    def test_multiple_funds(self, mock_nav, mock_metal):
        rows = [
            {"FundName": "Fund A", "Units": 100.0, "Identifier": "111111"},
            {"FundName": "Fund B", "Units": 200.0, "Identifier": "222222"},
            {"FundName": "Fund C", "Units":  50.0, "Identifier": "333333"},
        ]
        path = _build_excel(_minimal_sheets(mf_rows=rows))
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            funds = result["data"]["mutual_funds"]
            assert len(funds) == 3
            total = result["data"]["mutual_funds_summary"]["total_current_value"]
            assert total == pytest.approx((100 + 200 + 50) * 50.0)
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestExcelParserErrors:
    def test_file_not_found(self):
        from dashboard.services.excel_parser import parse_excel_file, ExcelParserError
        with pytest.raises(ExcelParserError):
            parse_excel_file("/nonexistent/path/file.xlsx")

    def test_missing_sheet_adds_warning(self, mock_nav, mock_metal):
        """Missing optional sheet should add warning, not crash."""
        sheets = _minimal_sheets()
        del sheets["MutualFunds"]   # drop MF sheet
        path = _build_excel(sheets)
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            assert result["success"] is True
            assert any("MutualFunds" in w for w in result["warnings"])
            assert result["data"]["mutual_funds"] == []
        finally:
            os.unlink(path)

    def test_missing_required_column_adds_error(self, mock_nav, mock_metal):
        """Wrong column names should add error."""
        rows = [{"WrongName": "Fund A", "Units": 100.0, "Identifier": "111111"}]
        path = _build_excel(_minimal_sheets(mf_rows=rows))
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            assert any("MutualFunds" in e for e in result["errors"])
        finally:
            os.unlink(path)

    def test_zero_units_handled(self, mock_nav, mock_metal):
        """Rows with zero units should not crash and contribute 0 value."""
        rows = [{"FundName": "Zero Fund", "Units": 0.0, "Identifier": "111111"}]
        path = _build_excel(_minimal_sheets(mf_rows=rows))
        try:
            from dashboard.services.excel_parser import parse_excel_file
            result = parse_excel_file(path)
            fund = result["data"]["mutual_funds"][0]
            assert fund["current_value"] == pytest.approx(0.0)
        finally:
            os.unlink(path)

    def test_nav_unavailable_triggers_warning(self, mock_metal):
        """If NAV service returns None, a warning is added and value = 0."""
        with patch("dashboard.services.excel_parser.get_nav_service") as mock_factory:
            adapter = mock_factory.return_value
            adapter.get_nav.return_value = (None, "Not Available")
            rows = [{"FundName": "No NAV Fund", "Units": 100.0, "Identifier": "BADCODE"}]
            path = _build_excel(_minimal_sheets(mf_rows=rows))
            try:
                from dashboard.services.excel_parser import parse_excel_file
                result = parse_excel_file(path)
                fund = result["data"]["mutual_funds"][0]
                assert fund["nav"] == 0.0
                assert fund["current_value"] == 0.0
                assert any("BADCODE" in w or "No NAV Fund" in w for w in result["warnings"])
            finally:
                os.unlink(path)


# ---------------------------------------------------------------------------
# Allocation correctness
# ---------------------------------------------------------------------------

class TestAllocationCorrectness:
    def test_allocation_sums_to_net_worth(self, mock_nav, mock_metal):
        path = _build_excel(_minimal_sheets())
        try:
            from dashboard.services.excel_parser import parse_excel_file
            from dashboard.services.calculation_engine import build_portfolio
            data = parse_excel_file(path)["data"]
            nw = build_portfolio(data).net_worth
            parts = (
                data["mutual_funds_summary"]["total_current_value"]
                + data["retirement_total"]
                + data["liquid_total"]
                + data["emergency_fund_total"]
                + data["metals_total"]
            )
            assert nw == pytest.approx(parts, rel=1e-6)
        finally:
            os.unlink(path)

    def test_total_investments_excludes_liquid(self, mock_nav, mock_metal):
        path = _build_excel(_minimal_sheets())
        try:
            from dashboard.services.excel_parser import parse_excel_file
            from dashboard.services.calculation_engine import build_portfolio
            data = parse_excel_file(path)["data"]
            portfolio = build_portfolio(data)
            ti = portfolio.mf_total + portfolio.retirement_total
            mf = data["mutual_funds_summary"]["total_current_value"]
            ret = data["retirement_total"]
            liq = data["liquid_total"]
            # investments = MF + Retirement (NOT liquid)
            assert ti == pytest.approx(mf + ret)
            assert ti != pytest.approx(mf + ret + liq)
        finally:
            os.unlink(path)
