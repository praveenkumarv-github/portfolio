from unittest.mock import patch

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