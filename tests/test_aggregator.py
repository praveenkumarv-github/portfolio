from unittest.mock import patch

import pytest


@pytest.mark.django_db
class TestAggregator:
    def test_build_dashboard_context_uses_mtime_cache(self, tmp_path):
        from dashboard.services.aggregator import build_dashboard_context, clear_dashboard_cache

        clear_dashboard_cache()
        xlsx = tmp_path / "portfolio.xlsx"
        xlsx.write_text("dummy", encoding="utf-8")

        fake_result = {
            "success": True,
            "data": {
                "mutual_funds_summary": {"total_current_value": 10},
                "retirement_total": 20,
                "liquid_total": 30,
                "emergency_fund_total": 40,
                "metals_total": 50,
                "insurance_summary": {"total_premium": 0, "total_coverage": 0},
                "mutual_funds": [],
                "retirement": [],
                "liquid": [],
                "emergency_fund": [],
                "emergency_fund_by_type": {},
                "metals": [],
                "insurance": [],
            },
            "errors": [],
            "warnings": [],
        }

        with patch("dashboard.services.aggregator.parse_excel_file", return_value=fake_result) as parse_mock:
            ctx1 = build_dashboard_context(str(xlsx))
            ctx2 = build_dashboard_context(str(xlsx))

        assert parse_mock.call_count == 1
        assert ctx1["portfolio"].net_worth == 150
        assert ctx2["portfolio"].net_worth == 150

    def test_clear_dashboard_cache_forces_reparse(self, tmp_path):
        from dashboard.services.aggregator import build_dashboard_context, clear_dashboard_cache

        clear_dashboard_cache()
        xlsx = tmp_path / "portfolio.xlsx"
        xlsx.write_text("dummy", encoding="utf-8")

        fake_result = {
            "success": True,
            "data": {
                "mutual_funds_summary": {"total_current_value": 1},
                "retirement_total": 1,
                "liquid_total": 1,
                "emergency_fund_total": 1,
                "metals_total": 1,
                "insurance_summary": {"total_premium": 0, "total_coverage": 0},
                "mutual_funds": [],
                "retirement": [],
                "liquid": [],
                "emergency_fund": [],
                "emergency_fund_by_type": {},
                "metals": [],
                "insurance": [],
            },
            "errors": [],
            "warnings": [],
        }

        with patch("dashboard.services.aggregator.parse_excel_file", return_value=fake_result) as parse_mock:
            build_dashboard_context(str(xlsx))
            clear_dashboard_cache()
            build_dashboard_context(str(xlsx))

        assert parse_mock.call_count == 2
