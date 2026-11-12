"""Gateway settings. Everything comes from environment variables (see .env.example)."""

import os
from dataclasses import dataclass

LOCAL_PORTAL_ORIGIN = "http://localhost:3000"


@dataclass(frozen=True)
class Settings:
    environment: str
    auth_mode: str  # "dev" (fixed test token) or "jwt" (real login tokens)
    dev_auth_token: str
    dev_user_id: str
    jwt_issuer: str
    jwt_audience: str
    jwt_jwks_url: str
    timeout_seconds: float
    upload_timeout_seconds: float
    cors_origins: list[str]
    log_level: str


def load_settings() -> Settings:
    """Read the settings once at start-up and stop with a clear message if they are unsafe."""
    environment = os.environ.get("ENVIRONMENT", "local")
    auth_mode = os.environ.get("AUTH_MODE", "dev")

    if auth_mode not in ("dev", "jwt"):
        raise ValueError(f"AUTH_MODE must be 'dev' or 'jwt', not '{auth_mode}'")
    # The fixed test token is a laptop convenience. It must never be accepted in the cloud.
    if auth_mode == "dev" and environment != "local":
        raise ValueError("AUTH_MODE=dev is only allowed when ENVIRONMENT=local")
    if auth_mode == "dev" and not os.environ.get("DEV_AUTH_TOKEN"):
        raise ValueError("AUTH_MODE=dev needs DEV_AUTH_TOKEN")
    if auth_mode == "jwt" and not os.environ.get("JWT_JWKS_URL"):
        raise ValueError("AUTH_MODE=jwt needs JWT_JWKS_URL")

    cors_origins = [LOCAL_PORTAL_ORIGIN]
    if os.environ.get("DEPLOYED_PORTAL_URL"):
        cors_origins.append(os.environ["DEPLOYED_PORTAL_URL"])

    return Settings(
        environment=environment,
        auth_mode=auth_mode,
        dev_auth_token=os.environ.get("DEV_AUTH_TOKEN", ""),
        dev_user_id=os.environ.get("DEV_USER_ID", "user-1"),
        jwt_issuer=os.environ.get("JWT_ISSUER", ""),
        jwt_audience=os.environ.get("JWT_AUDIENCE", ""),
        jwt_jwks_url=os.environ.get("JWT_JWKS_URL", ""),
        timeout_seconds=float(os.environ.get("GATEWAY_TIMEOUT_SECONDS", "10")),
        upload_timeout_seconds=float(os.environ.get("GATEWAY_UPLOAD_TIMEOUT_SECONDS", "300")),
        cors_origins=cors_origins,
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
    )
