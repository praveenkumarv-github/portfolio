import copy

import pytest

from scripts.patch_zappa_settings import patch_settings


BASE_CONFIG = {
    "production": {
        "role_arn": "arn:aws:iam::123456789012:role/existing",
        "s3_bucket": "existing-bucket",
        "environment_variables": {"GOOGLE_SERVICE_ACCOUNT_JSON": "must-not-survive"},
    }
}


def _environment(**overrides):
    environment = {
        "ZAPPA_STAGE": "production",
        "DJANGO_SECRET_KEY": "test-secret-with-at-least-fifty-random-looking-characters-123",
        "ALLOWED_HOSTS": "finance.example.com,.amazonaws.com",
        "GOOGLE_SERVICE_ACCOUNT_SECRET_ID": "finance-dash/google-service-account",
        "CLOUDFLARE_ACCESS_ENABLED": "true",
        "CLOUDFLARE_ACCESS_TEAM_DOMAIN": "https://personal.cloudflareaccess.com",
        "CLOUDFLARE_ACCESS_AUDIENCE": "audience",
        "CLOUDFLARE_ACCESS_ALLOWED_EMAIL": "owner@example.com",
    }
    environment.update(overrides)
    return environment


def test_patch_produces_secure_lambda_configuration():
    config = patch_settings(copy.deepcopy(BASE_CONFIG), _environment())
    production = config["production"]
    variables = production["environment_variables"]

    assert production["project_name"] == "portfolio"
    assert production["runtime"] == "python3.11"
    assert production["ephemeral_storage"] == {"Size": 3072}
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" not in variables
    assert variables["GOOGLE_SERVICE_ACCOUNT_SECRET_ID"] == "finance-dash/google-service-account"
    assert variables["CLOUDFLARE_ACCESS_ENABLED"] == "true"


def test_patch_uses_terraform_outputs_when_present():
    config = patch_settings(
        copy.deepcopy(BASE_CONFIG),
        _environment(TF_ROLE_ARN="arn:aws:iam::123456789012:role/from-terraform", TF_S3_BUCKET="tf-bucket"),
    )
    assert config["production"]["role_arn"].endswith("from-terraform")
    assert config["production"]["s3_bucket"] == "tf-bucket"


@pytest.mark.parametrize("missing", ["DJANGO_SECRET_KEY", "ALLOWED_HOSTS", "CLOUDFLARE_ACCESS_AUDIENCE"])
def test_patch_fails_when_required_security_setting_is_missing(missing):
    with pytest.raises(ValueError, match=missing):
        patch_settings(copy.deepcopy(BASE_CONFIG), _environment(**{missing: ""}))


def test_explicitly_disabled_access_removes_identity_configuration():
    config = patch_settings(
        copy.deepcopy(BASE_CONFIG),
        _environment(CLOUDFLARE_ACCESS_ENABLED="false", CLOUDFLARE_ACCESS_AUDIENCE=""),
    )
    variables = config["production"]["environment_variables"]
    assert variables["CLOUDFLARE_ACCESS_ENABLED"] == "false"
    assert "CLOUDFLARE_ACCESS_AUDIENCE" not in variables