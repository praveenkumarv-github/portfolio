from datetime import date

import pytest

from dashboard.services.capital_gains import classify_holding_periods


class TestFIFOLotMatching:
    def test_short_term_redemption_uses_oldest_lot(self):
        txns = [
            {"date": date(2026, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0},
            {"date": date(2026, 1, 31), "type": "Redeemed", "units": 50.0, "nav": 12.0},
        ]
        result = classify_holding_periods(txns, current_nav=12.0, as_of=date(2026, 1, 31))
        assert result["realized_short_term_gain"] == pytest.approx(50.0 * (12.0 - 10.0))
        assert result["realized_short_term_units"] == pytest.approx(50.0)
        assert result["realized_long_term_gain"] == pytest.approx(0.0)

    def test_long_term_redemption_after_365_days(self):
        txns = [
            {"date": date(2025, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0},
            {"date": date(2026, 2, 1), "type": "Redeemed", "units": 50.0, "nav": 15.0},
        ]
        result = classify_holding_periods(txns, current_nav=15.0, as_of=date(2026, 2, 1))
        assert result["realized_long_term_gain"] == pytest.approx(50.0 * (15.0 - 10.0))
        assert result["realized_long_term_units"] == pytest.approx(50.0)
        assert result["realized_short_term_gain"] == pytest.approx(0.0)

    def test_redemption_splits_fifo_across_two_lots(self):
        txns = [
            {"date": date(2025, 1, 1), "type": "Invested", "units": 60.0, "nav": 10.0},   # long-term by sale date
            {"date": date(2026, 1, 15), "type": "Invested", "units": 60.0, "nav": 12.0},  # short-term by sale date
            {"date": date(2026, 2, 1), "type": "Redeemed", "units": 100.0, "nav": 20.0},
        ]
        result = classify_holding_periods(txns, current_nav=20.0, as_of=date(2026, 2, 1))
        # FIFO consumes all 60 from lot 1 (>=365 days held) then 40 from lot 2 (<365 days held)
        assert result["realized_long_term_units"] == pytest.approx(60.0)
        assert result["realized_long_term_gain"] == pytest.approx(60.0 * (20.0 - 10.0))
        assert result["realized_short_term_units"] == pytest.approx(40.0)
        assert result["realized_short_term_gain"] == pytest.approx(40.0 * (20.0 - 12.0))
        # remaining 20 units of lot 2 are still held (unrealized, short-term)
        assert result["unrealized_short_term_units"] == pytest.approx(20.0)
        assert result["unrealized_short_term_gain"] == pytest.approx(20.0 * (20.0 - 12.0))
        assert result["unrealized_long_term_units"] == pytest.approx(0.0)

    def test_unrealized_split_long_vs_short(self):
        txns = [
            {"date": date(2025, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0},
            {"date": date(2026, 1, 15), "type": "Invested", "units": 100.0, "nav": 11.0},
        ]
        result = classify_holding_periods(txns, current_nav=15.0, as_of=date(2026, 2, 1))
        assert result["unrealized_long_term_units"] == pytest.approx(100.0)
        assert result["unrealized_long_term_gain"] == pytest.approx(100.0 * (15.0 - 10.0))
        assert result["unrealized_short_term_units"] == pytest.approx(100.0)
        assert result["unrealized_short_term_gain"] == pytest.approx(100.0 * (15.0 - 11.0))

    def test_missing_current_nav_yields_zero_unrealized_gain_but_keeps_units(self):
        txns = [
            {"date": date(2025, 1, 1), "type": "Invested", "units": 100.0, "nav": 10.0},
        ]
        result = classify_holding_periods(txns, current_nav=0.0, as_of=date(2026, 2, 1))
        assert result["unrealized_long_term_units"] == pytest.approx(100.0)
        assert result["unrealized_long_term_gain"] == pytest.approx(0.0)

    def test_no_transactions_returns_zeroed_result(self):
        result = classify_holding_periods([], current_nav=10.0, as_of=date(2026, 1, 1))
        assert result["realized_long_term_gain"] == 0.0
        assert result["unrealized_short_term_units"] == 0.0
