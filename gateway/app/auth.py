"""Login check. ONE function, verify_token(), decides who the caller is.

- AUTH_MODE=dev (laptop only): the fixed DEV_AUTH_TOKEN from .env means user DEV_USER_ID.
- AUTH_MODE=jwt (cloud): a real login token, checked against the login provider's public keys
  (JWT_JWKS_URL). Salem configures the provider (Cognito or another OIDC provider).
"""

import hmac
from functools import lru_cache

import jwt

from app.config import Settings


class AuthError(Exception):
    """The caller is not logged in (answered with 401)."""


def bearer_token(authorization_header: str | None) -> str:
    """Take the token out of 'Authorization: Bearer <token>'."""
    if not authorization_header:
        raise AuthError("Missing Authorization header")
    scheme, _, token = authorization_header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("Authorization header must be 'Bearer <token>'")
    return token.strip()


def verify_token(token: str, settings: Settings) -> str:
    """Return the user ID for a valid token, or raise AuthError."""
    if settings.auth_mode == "dev":
        return _verify_dev_token(token, settings)
    return _verify_jwt(token, settings)


def _verify_dev_token(token: str, settings: Settings) -> str:
    # compare_digest takes the same time for every wrong token, so it cannot be guessed bit by bit
    if not hmac.compare_digest(token.encode(), settings.dev_auth_token.encode()):
        raise AuthError("Invalid token")
    return settings.dev_user_id


@lru_cache(maxsize=1)
def _jwks_client(jwks_url: str) -> jwt.PyJWKClient:
    # The client downloads the provider's public keys once and keeps them in memory.
    return jwt.PyJWKClient(jwks_url)


def _verify_jwt(token: str, settings: Settings) -> str:
    try:
        signing_key = _jwks_client(settings.jwt_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.jwt_audience or None,
            issuer=settings.jwt_issuer or None,
            options={"verify_aud": bool(settings.jwt_audience), "require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as error:
        raise AuthError("Invalid or expired token") from error
    return claims["sub"]
