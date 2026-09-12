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

    def test_arbitrage_fund_prefers_hybrid_over_growth_keyword(self):
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 1000.0},
            "retirement_total": 0.0,
            "liquid_total": 0.0,
            "emergency_fund_total": 0.0,
            "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Sundaram Arbitrage Fund Direct Growth", "current_value": 250.0, "fund_type": ""},
                {"fund_name": "Bluechip Equity Fund", "current_value": 750.0, "fund_type": ""},
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
        assert split["Hybrid"] == pytest.approx(250.0)
        assert split["Equity"] == pytest.approx(750.0)

    def test_negative_asset_rows_are_ignored_consistently(self):
        from dashboard.services.calculation_engine import build_portfolio
        from dashboard.services.validators import validate_portfolio_data

        data = {
            "mutual_funds_summary": {"total_current_value": 900.0},
            "retirement_total": 50.0,
            "liquid_total": 90.0,
            "emergency_fund_total": 75.0,
            "metals_total": 150.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Positive Fund", "current_value": 1000.0, "fund_type": ""},
                {"fund_name": "Negative Fund", "current_value": -100.0, "fund_type": ""},
            ],
            "retirement": [
                {"type": "Pension", "amount": 100.0},
                {"type": "Adjustment", "amount": -50.0},
            ],
            "liquid": [
                {"account_name": "Cash", "type": "Savings", "amount": 100.0},
                {"account_name": "Correction", "type": "Savings", "amount": -10.0},
            ],
            "emergency_fund": [
                {"account_name": "EF1", "type": "FD", "amount": 100.0, "maturity_date": ""},
                {"account_name": "EF2", "type": "FD", "amount": -25.0, "maturity_date": ""},
            ],
            "emergency_fund_by_type": {"FD": 75.0},
            "metals": [
                {"type": "Gold", "quantity": 1.0, "price_per_gram": 200.0, "price_source": "Manual", "value": 200.0},
                {"type": "Silver", "quantity": 1.0, "price_per_gram": -50.0, "price_source": "Manual", "value": -50.0},
            ],
            "insurance": [],
        }

        warnings = validate_portfolio_data(data)
        assert any("Negative mutual fund value" in warning for warning in warnings)
        assert any("Negative retirement amount" in warning for warning in warnings)
        assert any("Negative liquid amount" in warning for warning in warnings)
        assert any("Negative emergency fund amount" in warning for warning in warnings)
        assert any("Negative metals value" in warning for warning in warnings)

        portfolio = build_portfolio(data)
        assert portfolio.net_worth == pytest.approx(1500.0)
        assert sum(category.value for category in portfolio.categories) == pytest.approx(portfolio.net_worth)
        assert sum(category.pct for category in portfolio.categories) == pytest.approx(100.0, abs=0.2)
        assert sum(item["value"] for item in portfolio.mf_split) == pytest.approx(portfolio.mf_total)
        assert sum(item["value"] for item in portfolio.retirement_split) == pytest.approx(portfolio.retirement_total)
        assert sum(item["value"] for item in portfolio.liquid_split) == pytest.approx(portfolio.liquid_total)
        assert sum(item["value"] for item in portfolio.emergency_fund_split) == pytest.approx(portfolio.emergency_fund_total)
        assert sum(item["value"] for item in portfolio.metals_split) == pytest.approx(portfolio.metals_total)

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

    def test_fund_analytics_computed_from_transaction_ledger(self):
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 44000.0},
            "retirement_total": 0.0,
            "liquid_total": 0.0,
            "emergency_fund_total": 0.0,
            "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {
                    "fund_name": "UTI Nifty 50 Index Fund Direct Growth",
                    "identifier": "120716",
                    "current_value": 44000.0,
                    "fund_type": "",
                },
            ],
            "retirement": [],
            "liquid": [],
            "emergency_fund": [],
            "emergency_fund_by_type": {},
            "metals": [],
            "insurance": [],
            "mf_transactions": [
                {
                    "identifier": "120716",
                    "date": date(2026, 8, 7),
                    "type": "Invested",
                    "units": 173.393,
                    "nav": 173.0145,
                    "amount": 29999.50,
                },
                {
                    "identifier": "120716",
                    "date": date(2026, 9, 3),
                    "type": "Invested",
                    "units": 59.48,
                    "nav": 168.12,
                    "amount": 10000.50,
                },
            ],
        }

        portfolio = build_portfolio(data)
        fund = portfolio.mutual_funds[0]
        assert fund["invested_amount"] == pytest.approx(40000.00, abs=0.01)
        assert fund["net_invested"] == pytest.approx(40000.00, abs=0.01)
        assert fund["first_investment_date"] == date(2026, 8, 7)
        assert len(fund["transactions"]) == 2
        assert fund["absolute_gain"] == pytest.approx(4000.00, abs=0.01)
        assert fund["absolute_return_pct"] == pytest.approx(10.0, abs=0.01)
        assert fund["xirr_pct"] is not None  # solvable: 2 outflows + 1 inflow, net positive

        assert portfolio.mf_analytics["has_transactions"] is True
        assert portfolio.mf_analytics["invested_amount"] == pytest.approx(40000.00, abs=0.01)

    def test_fund_without_transactions_has_null_analytics(self):
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 500.0},
            "retirement_total": 0.0,
            "liquid_total": 0.0,
            "emergency_fund_total": 0.0,
            "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "No History Fund", "identifier": "999999", "current_value": 500.0, "fund_type": ""},
            ],
            "retirement": [],
            "liquid": [],
            "emergency_fund": [],
            "emergency_fund_by_type": {},
            "metals": [],
            "insurance": [],
        }

        portfolio = build_portfolio(data)
        fund = portfolio.mutual_funds[0]
        assert fund["transactions"] == []
        assert fund["xirr_pct"] is None
        assert fund["absolute_return_pct"] is None
        assert portfolio.mf_analytics["has_transactions"] is False

    def test_pooled_analytics_ignores_untracked_funds_current_value(self):
        """Regression: pooled gain must not count untracked funds' current
        value as if it were investment growth."""
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 1100.0},
            "retirement_total": 0.0,
            "liquid_total": 0.0,
            "emergency_fund_total": 0.0,
            "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Tracked Fund", "identifier": "1", "current_value": 1100.0, "fund_type": ""},
                {"fund_name": "Untracked Fund", "identifier": "2", "current_value": 5000.0, "fund_type": ""},
            ],
            "retirement": [],
            "liquid": [],
            "emergency_fund": [],
            "emergency_fund_by_type": {},
            "metals": [],
            "insurance": [],
            "mf_transactions": [
                {"identifier": "1", "date": date(2025, 1, 1), "type": "Invested", "units": 10, "nav": 100.0, "amount": 1000.0},
            ],
        }

        portfolio = build_portfolio(data)
        assert portfolio.mf_analytics["tracked_current_value"] == pytest.approx(1100.0)
        assert portfolio.mf_analytics["net_invested"] == pytest.approx(1000.0)
        # gain must be 1100-1000=100, NOT 1100+5000-1000=5100
        assert portfolio.mf_analytics["absolute_gain"] == pytest.approx(100.0)

    def test_avg_cost_nav_and_cagr_computed_per_fund(self):
        from datetime import date, timedelta
        from dashboard.services.calculation_engine import build_portfolio

        first_date = date.today() - timedelta(days=730)
        data = {
            "mutual_funds_summary": {"total_current_value": 2000.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Fund A", "identifier": "A1", "current_value": 2000.0, "nav": 20.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                {"identifier": "A1", "date": first_date, "type": "Invested", "units": 100.0, "nav": 10.0, "amount": 1000.0},
            ],
        }
        portfolio = build_portfolio(data)
        fund = portfolio.mutual_funds[0]
        assert fund["avg_cost_nav"] == pytest.approx(10.0)
        assert fund["cagr_pct"] is not None
        assert fund["cagr_pct"] > 0  # current_value(2000) > invested(1000) over 2 years

    def test_best_and_worst_fund_ranking(self):
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 2200.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Winner Fund", "identifier": "W1", "current_value": 2000.0, "nav": 20.0, "fund_type": ""},
                {"fund_name": "Loser Fund", "identifier": "L1", "current_value": 200.0, "nav": 2.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                {"identifier": "W1", "date": date(2025, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0, "amount": 1000.0},
                {"identifier": "L1", "date": date(2025, 1, 1), "type": "Invested", "units": 100.0, "nav": 3.0, "amount": 300.0},
            ],
        }
        portfolio = build_portfolio(data)
        assert portfolio.mf_analytics["best_fund"]["identifier"] == "W1"
        assert portfolio.mf_analytics["worst_fund"]["identifier"] == "L1"

    def test_portfolio_capital_gains_rollup_sums_across_funds(self):
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 3000.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Fund A", "identifier": "A1", "current_value": 1500.0, "nav": 15.0, "fund_type": ""},
                {"fund_name": "Fund B", "identifier": "B1", "current_value": 1500.0, "nav": 15.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                # Fund A: long-term holding (>365 days) -> unrealized long-term gain
                {"identifier": "A1", "date": date(2025, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0, "amount": 1000.0},
                # Fund B: short-term holding (<365 days) -> unrealized short-term gain
                {"identifier": "B1", "date": date(2026, 6, 1), "type": "Invested", "units": 100.0, "nav": 10.0, "amount": 1000.0},
            ],
        }
        portfolio = build_portfolio(data)
        cg = portfolio.mf_analytics["capital_gains"]
        assert cg["unrealized_long_term_gain"] == pytest.approx(500.0)
        assert cg["unrealized_short_term_gain"] == pytest.approx(500.0)

    def test_transaction_current_value_annotated_for_invested_rows(self):
        from datetime import date, timedelta
        from dashboard.services.calculation_engine import build_portfolio

        purchase_date = date.today() - timedelta(days=400)  # long-term by today
        data = {
            "mutual_funds_summary": {"total_current_value": 2000.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Sundaram Arbitrage Fund Direct Growth", "identifier": "149550", "current_value": 2000.0, "nav": 20.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                {"identifier": "149550", "date": purchase_date, "type": "Invested", "units": 169.47, "nav": 15.34, "amount": 2599.0},
            ],
        }
        portfolio = build_portfolio(data)
        txn = portfolio.mutual_funds[0]["transactions"][0]
        assert txn["current_value"] == pytest.approx(169.47 * 20.0)
        assert txn["gain"] == pytest.approx((169.47 * 20.0) - 2599.0)
        assert txn["holding_period"] == "Long-Term"

    def test_redeemed_rows_have_no_current_value(self):
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 1000.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Fund A", "identifier": "A1", "current_value": 1000.0, "nav": 10.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                {"identifier": "A1", "date": date(2025, 1, 1), "type": "Invested", "units": 200.0, "nav": 5.0, "amount": 1000.0},
                {"identifier": "A1", "date": date(2025, 6, 1), "type": "Redeemed", "units": 100.0, "nav": 8.0, "amount": 800.0},
            ],
        }
        portfolio = build_portfolio(data)
        txns = portfolio.mutual_funds[0]["transactions"]
        redeemed = next(t for t in txns if t["type"] == "Redeemed")
        assert redeemed["current_value"] is None
        assert redeemed["holding_period"] is None

    def test_purchase_lot_ledger_flattened_across_funds_sorted_desc(self):
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 3000.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Fund A", "identifier": "A1", "current_value": 1500.0, "nav": 15.0, "fund_type": ""},
                {"fund_name": "Fund B", "identifier": "B1", "current_value": 1500.0, "nav": 15.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                {"identifier": "A1", "date": date(2026, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0, "amount": 1000.0},
                {"identifier": "B1", "date": date(2026, 3, 1), "type": "Invested", "units": 100.0, "nav": 10.0, "amount": 1000.0},
            ],
        }
        portfolio = build_portfolio(data)
        lots = portfolio.mf_purchase_lots
        assert len(lots) == 2
        assert lots[0]["fund_name"] == "Fund B"  # most recent purchase first
        assert lots[0]["current_value"] == pytest.approx(1500.0)

    def test_purchase_summary_groups_multiple_lots_per_fund(self):
        from datetime import date
        from dashboard.services.calculation_engine import build_portfolio

        data = {
            "mutual_funds_summary": {"total_current_value": 2000.0},
            "retirement_total": 0.0, "liquid_total": 0.0, "emergency_fund_total": 0.0, "metals_total": 0.0,
            "insurance_summary": {"total_premium": 0.0, "total_coverage": 0.0},
            "mutual_funds": [
                {"fund_name": "Fund A", "identifier": "A1", "current_value": 2000.0, "nav": 10.0, "fund_type": ""},
            ],
            "retirement": [], "liquid": [], "emergency_fund": [], "emergency_fund_by_type": {},
            "metals": [], "insurance": [],
            "mf_transactions": [
                {"identifier": "A1", "date": date(2026, 1, 1), "type": "Invested", "units": 100.0, "nav": 8.0, "amount": 800.0},
                {"identifier": "A1", "date": date(2026, 2, 1), "type": "Invested", "units": 100.0, "nav": 9.0, "amount": 900.0},
            ],
        }
        portfolio = build_portfolio(data)
        summary = portfolio.mf_purchase_summary
        assert len(summary) == 1
        row = summary[0]
        assert row["units"] == pytest.approx(200.0)
        assert row["invested_amount"] == pytest.approx(1700.0)
        assert row["current_value"] == pytest.approx(2000.0)
        assert row["gain"] == pytest.approx(300.0)
        assert row["purchase_count"] == 2

