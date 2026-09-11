from datetime import date

import pytest

from dashboard.services.xirr import xirr


class TestXirr:
    def test_simple_one_year_ten_percent(self):
        cashflows = [(date(2025, 1, 1), -1000.0), (date(2026, 1, 1), 1100.0)]
        rate = xirr(cashflows)
        assert rate == pytest.approx(0.10, abs=1e-4)

    def test_sip_like_multiple_investments(self):
        cashflows = [
            (date(2025, 1, 1), -10000.0),
            (date(2025, 7, 1), -10000.0),
            (date(2026, 1, 1), 22000.0),
        ]
        rate = xirr(cashflows)
        assert rate is not None
        assert rate > 0

    def test_loss_position_returns_negative_rate(self):
        cashflows = [(date(2025, 1, 1), -1000.0), (date(2026, 1, 1), 800.0)]
        rate = xirr(cashflows)
        assert rate == pytest.approx(-0.20, abs=1e-3)

    def test_insufficient_cashflows_returns_none(self):
        assert xirr([]) is None
        assert xirr([(date(2025, 1, 1), -1000.0)]) is None

    def test_all_same_sign_returns_none(self):
        cashflows = [(date(2025, 1, 1), -1000.0), (date(2026, 1, 1), -500.0)]
        assert xirr(cashflows) is None

    def test_unordered_input_still_solves(self):
        cashflows = [(date(2026, 1, 1), 1100.0), (date(2025, 1, 1), -1000.0)]
        rate = xirr(cashflows)
        assert rate == pytest.approx(0.10, abs=1e-4)
