import pytest


class TestCalculationEngine:
    def test_mf_split_equity_debt_hybrid(self):
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 1000.0},
            "retirement_total": 0.0,
            "liquid_total": 0.0,
            "emergency_fund_total": 0.0,
            "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Bluechip Equity Fund", "current_value": 500.0, "fund_type": ""},
                {"fund_name": "Corporate Bond Debt Fund", "current_value": 300.0, "fund_type": ""},
                {"fund_name": "Balanced Advantage Hybrid", "current_value": 200.0, "fund_type": ""},
            ],
            "retirement": [],
            "liquid": [],
            "emergency_fund": [],
            "emergency_fund_by_type": {},
            "metals": [],
            "insurance": [],
        }

        portfolio = build_portfolio(data)
        split = {x["type"]: x["value"] for x in portfolio.mf_split}
        assert split["Equity"] == pytest.approx(500.0)
        assert split["Debt"] == pytest.approx(300.0)
        assert split["Hybrid"] == pytest.approx(200.0)
        assert sum(split.values()) == pytest.approx(portfolio.mf_total)

    def test_allocation_excludes_insurance(self):
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 200.0},
            "retirement_total": 300.0,
            "liquid_total": 100.0,
            "emergency_fund_total": 50.0,
            "metals_total": 350.0,
            "insurance_summary": {"total_premium": 15000.0, "total_coverage": 10000000.0},
            "mutual_funds": [],
            "retirement": [],
            "liquid": [],
            "emergency_fund": [],
            "emergency_fund_by_type": {},
            "metals": [],
            "insurance": [{"type": "Term", "provider": "LIC", "premium": 15000.0, "coverage": 10000000.0}],
        }

        portfolio = build_portfolio(data)
        assert portfolio.net_worth == pytest.approx(1000.0)
        total_pct = sum(c.pct for c in portfolio.categories)
        assert total_pct == pytest.approx(100.0)
