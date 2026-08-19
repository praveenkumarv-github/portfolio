import logging
from functools import lru_cache

import jwt
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponseForbidden


logger = logging.getLogger(__name__)


@lru_cache(maxsize=4)
def _jwk_client(certs_url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(certs_url, cache_keys=True, timeout=3)


def _decode_access_token(token: str, team_domain: str, audience: str) -> dict:
    certs_url = f"{team_domain}/cdn-cgi/access/certs"
    signing_key = _jwk_client(certs_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        audience=audience,
        issuer=team_domain,
        options={"require": ["exp", "iat", "iss", "aud", "email"]},
    )


class CloudflareAccessMiddleware:
    """Require a valid Cloudflare Access identity at the Lambda origin."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.enabled = getattr(settings, "CLOUDFLARE_ACCESS_ENABLED", False)
        self.team_domain = getattr(settings, "CLOUDFLARE_ACCESS_TEAM_DOMAIN", "").rstrip("/")
        self.audience = getattr(settings, "CLOUDFLARE_ACCESS_AUDIENCE", "")
        self.allowed_email = getattr(settings, "CLOUDFLARE_ACCESS_ALLOWED_EMAIL", "").lower()

        if self.enabled and not all((self.team_domain, self.audience, self.allowed_email)):
            raise ImproperlyConfigured(
                "Cloudflare Access requires team domain, audience, and allowed email"
            )

    def __call__(self, request):
        if not self.enabled:
            return self.get_response(request)

        token = request.headers.get("Cf-Access-Jwt-Assertion", "")
        if not token:
            return HttpResponseForbidden("Access denied")

        try:
            claims = _decode_access_token(token, self.team_domain, self.audience)
        except jwt.PyJWTError as exc:
            logger.warning("Cloudflare Access token rejected: %s", type(exc).__name__)
            return HttpResponseForbidden("Access denied")
        except Exception as exc:
            logger.error("Cloudflare Access verification unavailable: %s", type(exc).__name__)
            return HttpResponseForbidden("Access denied")

        if str(claims.get("email", "")).lower() != self.allowed_email:
            logger.warning("Cloudflare Access identity is not authorized")
            return HttpResponseForbidden("Access denied")

        request.cloudflare_access_identity = claims
        return self.get_response(request)