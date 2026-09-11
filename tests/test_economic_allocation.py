import pytest


def _base_portfolio(**overrides):
    """Minimal stand-in object exposing the attributes economic_allocation reads."""
    class _P:
        pass

    p = _P()
    p.net_worth = overrides.get("net_worth", 0.0)
    p.mutual_funds = overrides.get("mutual_funds", [])
    p.retirement = overrides.get("retirement", [])
    p.liquid = overrides.get("liquid", [])
    p.emergency_fund = overrides.get("emergency_fund", [])
    p.metals = overrides.get("metals", [])
    p.mf_split = overrides.get("mf_split", [])
    return p


class TestEconomicAllocation:
    def test_default_mix_classification_and_bucket_totals(self):
        from dashboard.services.economic_allocation import build_economic_allocation

        portfolio = _base_portfolio(
            net_worth=1000.0,
            mutual_funds=[
                {"fund_name": "Bluechip Equity Fund", "identifier": "1", "current_value": 400.0, "fund_type": ""},
                {"fund_name": "Corporate Bond Debt Fund", "identifier": "2", "current_value": 200.0, "fund_type": ""},
            ],
            retirement=[{"type": "PF", "amount": 200.0}],
            liquid=[{"account_name": "Savings", "type": "Savings", "amount": 100.0}],
            metals=[{"type": "Gold", "value": 100.0}],
            mf_split=[{"type": "Equity", "value": 400.0}],
        )

        result = build_economic_allocation({}, portfolio)
        buckets = {b["key"]: b for b in result["buckets"]}

        # Equity fund -> 100% Equity; PF -> 85% Govt Sec + 15% Equity; Cash -> 100% Cash; Gold -> 100% Gold
        assert buckets["equity"]["value"] == pytest.approx(400.0 + 200.0 * 0.15)
        assert buckets["corporate_debt"]["value"] == pytest.approx(200.0)
        assert buckets["govt_securities"]["value"] == pytest.approx(200.0 * 0.85)
        assert buckets["cash"]["value"] == pytest.approx(100.0)
        assert buckets["gold"]["value"] == pytest.approx(100.0)

        total = sum(b["value"] for b in result["buckets"])
        assert total == pytest.approx(portfolio.net_worth)

    def test_nps_without_override_is_unclassified(self):
        from dashboard.services.economic_allocation import build_economic_allocation

        portfolio = _base_portfolio(
            net_worth=500.0,
            retirement=[{"type": "NPS", "amount": 500.0}],
        )

        result = build_economic_allocation({}, portfolio)
        buckets = {b["key"]: b for b in result["buckets"]}
        assert buckets["other"]["value"] == pytest.approx(500.0)
        assert result["unclassified_notes"], "expected a note explaining why NPS is unclassified"

    def test_lookthrough_override_wins_over_default(self):
        from dashboard.services.economic_allocation import build_economic_allocation

        portfolio = _base_portfolio(
            net_worth=500.0,
            retirement=[{"type": "NPS", "amount": 500.0}],
        )
        data = {
            "lookthrough_overrides": [
                {"key": "NPS", "equity": 50.0, "corporate_debt": 30.0, "govt_securities": 20.0, "cash": 0.0, "gold": 0.0, "other": 0.0,
                 "equity_large": 0, "equity_mid": 0, "equity_small": 0, "equity_intl": 0},
            ],
        }

        result = build_economic_allocation(data, portfolio)
        buckets = {b["key"]: b for b in result["buckets"]}
        assert buckets["equity"]["value"] == pytest.approx(250.0)
        assert buckets["corporate_debt"]["value"] == pytest.approx(150.0)
        assert buckets["govt_securities"]["value"] == pytest.approx(100.0)
        assert buckets["other"]["value"] == pytest.approx(0.0)
        assert result["has_overrides"] is True

    def test_target_deviation_computed_when_targets_present(self):
        from dashboard.services.economic_allocation import build_economic_allocation

        portfolio = _base_portfolio(
            net_worth=1000.0,
            mutual_funds=[{"fund_name": "Equity Fund", "identifier": "1", "current_value": 1000.0, "fund_type": ""}],
        )
        data = {"targets": {"Equity": 50.0}}

        result = build_economic_allocation(data, portfolio)
        equity_bucket = next(b for b in result["buckets"] if b["key"] == "equity")
        assert equity_bucket["pct"] == pytest.approx(100.0)
        assert equity_bucket["target_pct"] == pytest.approx(50.0)
        assert equity_bucket["deviation_pct"] == pytest.approx(50.0)
        assert result["has_targets"] is True

    def test_hidden_equity_exposure_via_epf(self):
        from dashboard.services.economic_allocation import build_economic_allocation

        portfolio = _base_portfolio(
            net_worth=1000.0,
            mutual_funds=[{"fund_name": "Sundaram Arbitrage Fund Direct Growth", "identifier": "1", "current_value": 200.0, "fund_type": ""}],
            retirement=[{"type": "PF", "amount": 800.0}],
            mf_split=[{"type": "Equity", "value": 0.0}],  # arbitrage classified as Hybrid, not "Equity" label
        )

        result = build_economic_allocation({}, portfolio)
        # naive equity label = 0 (arbitrage isn't labelled Equity), but look-through finds
        # 20% of the arbitrage fund + 15% of PF as real equity exposure.
        assert result["naive_equity_pct"] == pytest.approx(0.0)
        assert result["effective_equity_pct"] > 0
        assert result["hidden_equity_delta_pct"] > 0

    def test_equity_style_split_from_override(self):
        from dashboard.services.economic_allocation import build_economic_allocation

        portfolio = _base_portfolio(
            net_worth=1000.0,
            mutual_funds=[{"fund_name": "Flexicap Fund", "identifier": "1", "current_value": 1000.0, "fund_type": ""}],
        )
        data = {
            "lookthrough_overrides": [
                {"key": "1", "equity": 100.0, "corporate_debt": 0, "govt_securities": 0, "cash": 0, "gold": 0, "other": 0,
                 "equity_large": 60.0, "equity_mid": 25.0, "equity_small": 15.0, "equity_intl": 0},
            ],
        }

        result = build_economic_allocation(data, portfolio)
        style = {s["key"]: s["value"] for s in result["equity_style"]}
        assert style["equity_large"] == pytest.approx(600.0)
        assert style["equity_mid"] == pytest.approx(250.0)
        assert style["equity_small"] == pytest.approx(150.0)
