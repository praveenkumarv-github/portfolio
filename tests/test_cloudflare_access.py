import time
from unittest.mock import patch

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from finance_dashboard.middleware import CloudflareAccessMiddleware


def _response(request):
    return HttpResponse("ok")


@override_settings(CLOUDFLARE_ACCESS_ENABLED=False)
def test_access_disabled_for_local_development():
    response = CloudflareAccessMiddleware(_response)(RequestFactory().get("/"))
    assert response.status_code == 200


@override_settings(
    CLOUDFLARE_ACCESS_ENABLED=True,
    CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://personal.cloudflareaccess.com",
    CLOUDFLARE_ACCESS_AUDIENCE="expected-audience",
    CLOUDFLARE_ACCESS_ALLOWED_EMAIL="owner@example.com",
)
def test_direct_origin_request_without_access_token_is_denied():
    response = CloudflareAccessMiddleware(_response)(RequestFactory().get("/"))
    assert response.status_code == 403


@override_settings(
    CLOUDFLARE_ACCESS_ENABLED=True,
    CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://personal.cloudflareaccess.com",
    CLOUDFLARE_ACCESS_AUDIENCE="expected-audience",
    CLOUDFLARE_ACCESS_ALLOWED_EMAIL="owner@example.com",
)
def test_valid_allowed_identity_is_accepted():
    request = RequestFactory().get("/", HTTP_CF_ACCESS_JWT_ASSERTION="signed-token")
    with patch(
        "finance_dashboard.middleware._decode_access_token",
        return_value={"email": "owner@example.com"},
    ):
        response = CloudflareAccessMiddleware(_response)(request)
    assert response.status_code == 200


@override_settings(
    CLOUDFLARE_ACCESS_ENABLED=True,
    CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://personal.cloudflareaccess.com",
    CLOUDFLARE_ACCESS_AUDIENCE="expected-audience",
    CLOUDFLARE_ACCESS_ALLOWED_EMAIL="owner@example.com",
)
def test_valid_but_unapproved_identity_is_denied():
    request = RequestFactory().get("/", HTTP_CF_ACCESS_JWT_ASSERTION="signed-token")
    with patch(
        "finance_dashboard.middleware._decode_access_token",
        return_value={"email": "someone-else@example.com"},
    ):
        response = CloudflareAccessMiddleware(_response)(request)
    assert response.status_code == 403


@pytest.fixture(scope="module")
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@override_settings(
    CLOUDFLARE_ACCESS_ENABLED=True,
    CLOUDFLARE_ACCESS_TEAM_DOMAIN="https://personal.cloudflareaccess.com",
    CLOUDFLARE_ACCESS_AUDIENCE="expected-audience",
    CLOUDFLARE_ACCESS_ALLOWED_EMAIL="owner@example.com",
)
@pytest.mark.parametrize("case,expected_status", [
    ("valid", 200),
    ("expired", 403),
    ("future_issued", 403),
    ("wrong_issuer", 403),
    ("wrong_audience", 403),
    ("wrong_email", 403),
    ("missing_exp", 403),
    ("missing_iat", 403),
    ("missing_iss", 403),
    ("missing_aud", 403),
    ("missing_email", 403),
    ("wrong_signature", 403),
    ("wrong_algorithm", 403),
    ("malformed", 403),
    ("jwks_unavailable", 403),
])
def test_real_signature_and_claim_validation(signing_key, case, expected_status):
    now = int(time.time())
    claims = {
        "exp": now + 300,
        "iat": now - 60,
        "iss": "https://personal.cloudflareaccess.com",
        "aud": "expected-audience",
        "email": "owner@example.com",
    }
    overrides = {
        "expired": {"exp": now - 30},
        "future_issued": {"iat": now + 300},
        "wrong_issuer": {"iss": "https://other.cloudflareaccess.com"},
        "wrong_audience": {"aud": "other-audience"},
        "wrong_email": {"email": "other@example.com"},
    }
    claims.update(overrides.get(case, {}))
    if case.startswith("missing_"):
        claims.pop(case.removeprefix("missing_"))

    token_key = signing_key
    algorithm = "RS256"
    if case == "wrong_signature":
        token_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    elif case == "wrong_algorithm":
        token_key = "synthetic-test-signing-key-not-a-production-secret"
        algorithm = "HS256"
    token = jwt.encode(claims, token_key, algorithm=algorithm, headers={"kid": "test-key"})
    if case == "malformed":
        token = "not-a-jwt"

    public_jwk = jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key(), as_dict=True)
    public_jwk["kid"] = "test-key"
    client = jwt.PyJWKClient("https://personal.cloudflareaccess.com/cdn-cgi/access/certs")
    failure = jwt.PyJWKClientConnectionError("synthetic outage") if case == "jwks_unavailable" else None
    request = RequestFactory().get("/", HTTP_CF_ACCESS_JWT_ASSERTION=token)
    with patch("finance_dashboard.middleware._jwk_client", return_value=client), patch.object(
        client, "fetch_data", return_value={"keys": [public_jwk]}, side_effect=failure
    ):
        response = CloudflareAccessMiddleware(_response)(request)

    assert response.status_code == expected_status
    if expected_status == 200:
        assert request.cloudflare_access_identity["email"] == "owner@example.com"
    else:
        assert response.content == b"Access denied"
        assert not hasattr(request, "cloudflare_access_identity")