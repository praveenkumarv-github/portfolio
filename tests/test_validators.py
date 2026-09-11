import pytest

from dashboard.services.validators import validate_portfolio_data


class TestMfTransactionReconciliation:
    def test_matching_units_no_warning(self):
        data = {
            "mutual_funds": [{"fund_name": "Fund A", "identifier": "1", "units": 100.0}],
            "mf_transactions": [
                {"identifier": "1", "type": "Invested", "units": 60.0},
                {"identifier": "1", "type": "Invested", "units": 40.0},
            ],
        }
        warnings = validate_portfolio_data(data)
        assert not any("MFTransactions" in w for w in warnings)

    def test_mismatched_units_warns(self):
        data = {
            "mutual_funds": [{"fund_name": "Fund A", "identifier": "1", "units": 100.0}],
            "mf_transactions": [
                {"identifier": "1", "type": "Invested", "units": 40.0},
            ],
        }
        warnings = validate_portfolio_data(data)
        assert any("MFTransactions" in w and "Fund A" in w for w in warnings)

    def test_redemptions_reduce_net_units(self):
        data = {
            "mutual_funds": [{"fund_name": "Fund A", "identifier": "1", "units": 50.0}],
            "mf_transactions": [
                {"identifier": "1", "type": "Invested", "units": 100.0},
                {"identifier": "1", "type": "Redeemed", "units": 50.0},
            ],
        }
        warnings = validate_portfolio_data(data)
        assert not any("MFTransactions" in w for w in warnings)

    def test_fund_without_transactions_is_not_checked(self):
        data = {
            "mutual_funds": [{"fund_name": "Fund A", "identifier": "1", "units": 100.0}],
            "mf_transactions": [],
        }
        warnings = validate_portfolio_data(data)
        assert not any("MFTransactions" in w for w in warnings)
