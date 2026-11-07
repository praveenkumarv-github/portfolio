"""
Edge-case tests for hardened pipeline behavior.
"""
from unittest.mock import patch
from pathlib import Path
import shutil
import subprocess

import pytest

from dashboard.services.calculation_engine import build_portfolio
from dashboard.services.validators import validate_portfolio_data


@pytest.mark.parametrize("inspection,expected_status", [("1", 0), ("None", 0), ("denied", 1)])
def test_cleanup_preserves_history_and_fails_closed(inspection, expected_status):
        bash = shutil.which("bash")
        if not bash:
                pytest.skip("bash is required to exercise the cleanup guard")
        source = (Path(__file__).resolve().parents[1] / "scripts/cleanup_aws_resources.sh").read_text(encoding="utf-8")
        function = "delete_s3_bucket() {" + source.split("delete_s3_bucket() {", 1)[1].split("\ndelete_secret()", 1)[0]
        stub = '''aws() {
            if [[ "$1 $2" != "s3api list-object-versions" || "$*" != *"--prefix net-worth/history/"* ]]; then
                echo "UNEXPECTED_AWS_OPERATION"
                return 87
            fi
            if [[ "$INSPECTION" == "denied" ]]; then return 1; fi
            printf '%s\\n' "$INSPECTION"
        }
        '''
        result = subprocess.run(
                [bash, "-s"], input=f"INSPECTION={inspection}\n" + stub + function + '\ndelete_s3_bucket "test-bucket"\n',
                text=True, capture_output=True, timeout=10,
        )
        assert result.returncode == expected_status
        assert "UNEXPECTED_AWS_OPERATION" not in result.stdout
        assert "[ACTION]" not in result.stdout
        assert "[SKIP]" in result.stdout if expected_status == 0 else "[ABORT]" in result.stdout


def _empty_data():
    return {
        "mutual_funds": [],
        "mutual_funds_summary": {"total_current_value": 0},
        "retirement": [],
        "retirement_total": 0,
        "liquid": [],
        "liquid_total": 0,
        "emergency_fund": [],
        "emergency_fund_total": 0,
        "emergency_fund_by_type": {},
        "metals": [],
        "metals_total": 0,
        "insurance": [],
        "insurance_summary": {"total_premium": 0, "total_coverage": 0},
    }


class TestEmptyDataset:
    def test_build_portfolio_handles_empty_data(self):
        portfolio = build_portfolio(_empty_data())
        assert portfolio.net_worth == 0
        assert portfolio.allocation_chart["values"] == []
        assert portfolio.categories  # 5 zero rows
        assert all(c.value == 0 for c in portfolio.categories)


class TestExtremeValues:
    @pytest.mark.parametrize("value", [float("inf"), -float("inf"), float("nan")])
    def test_nonfinite_values_are_rejected_before_charts(self, value):
        data = _empty_data()
        data["liquid_total"] = value
        with pytest.raises(ValueError, match="Non-finite"):
            build_portfolio(data)

    def test_overflowed_net_worth_is_rejected(self):
        data = _empty_data()
        data["liquid_total"] = 1e308
        data["retirement_total"] = 1e308
        with pytest.raises(ValueError, match="net_worth"):
            build_portfolio(data)

    def test_extreme_values_do_not_crash(self):
        data = _empty_data()
        data["mutual_funds_summary"]["total_current_value"] = 1e15
        data["retirement_total"] = 1e15
        data["mutual_funds"] = [{
            "fund_name": "Big",
            "identifier": "X",
            "units": 1e9,
            "nav": 999.99,
            "nav_source": "AMFI",
            "current_value": 1e15,
        }]
        portfolio = build_portfolio(data)
        assert portfolio.net_worth == pytest.approx(2e15)
        # Allocation percentages stay finite
        assert all(0 <= c.pct <= 100 for c in portfolio.categories)


class TestValidatorWarnings:
    def test_nav_out_of_bounds_triggers_warning(self):
        data = _empty_data()
        data["mutual_funds"] = [{
            "fund_name": "Bad NAV",
            "identifier": "X",
            "nav": 50_000.0,
        }]
        warnings = validate_portfolio_data(data)
        assert any("NAV out of bounds" in w for w in warnings)

    def test_metal_price_out_of_bounds_triggers_warning(self):
        data = _empty_data()
        data["metals"] = [{"type": "Gold", "price_per_gram": 999.0, "value": 0}]
        warnings = validate_portfolio_data(data)
        assert any("Gold price out of bounds" in w for w in warnings)

    def test_negative_total_triggers_warning(self):
        data = _empty_data()
        data["liquid_total"] = -100
        warnings = validate_portfolio_data(data)
        assert any("Negative total" in w for w in warnings)

    def test_validator_never_raises_on_garbage(self):
        assert validate_portfolio_data({}) == []
        assert validate_portfolio_data({"mutual_funds": [{"nav": "abc"}]}) == []


@pytest.mark.django_db
class TestAggregatorResilience:
    def test_parser_error_returns_clean_payload(self, tmp_path):
        from dashboard.services.aggregator import build_dashboard_context, clear_dashboard_cache
        from dashboard.services.excel_parser import ExcelParserError

        clear_dashboard_cache()
        xlsx = tmp_path / "broken.xlsx"
        xlsx.write_text("dummy", encoding="utf-8")

        with patch(
            "dashboard.services.aggregator.parse_excel_file",
            side_effect=ExcelParserError("corrupt file"),
        ):
            ctx = build_dashboard_context(str(xlsx))

        assert ctx["portfolio"] is None
        assert any("corrupt file" in e for e in ctx["errors"])

    def test_partial_data_still_renders_portfolio(self, tmp_path):
        from dashboard.services.aggregator import build_dashboard_context, clear_dashboard_cache

        clear_dashboard_cache()
        xlsx = tmp_path / "partial.xlsx"
        xlsx.write_text("dummy", encoding="utf-8")

        partial = {
            "success": True,
            "data": {
                **_empty_data(),
                "liquid_total": 50_000,
                "liquid": [{"account_name": "SBI", "type": "Savings", "amount": 50_000}],
            },
            "errors": [],
            "warnings": ["MutualFunds sheet missing"],
        }

        with patch("dashboard.services.aggregator.parse_excel_file", return_value=partial):
            ctx = build_dashboard_context(str(xlsx))

        assert ctx["portfolio"] is not None
        assert ctx["portfolio"].net_worth == 50_000
        assert any("MutualFunds" in w for w in ctx["warnings"])
