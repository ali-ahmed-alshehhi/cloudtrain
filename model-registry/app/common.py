"""Small helpers every stand-in uses (the same file is in each stand-in folder).

They give a service the shared rules: the error format, request IDs, one JSON log line per
request, GET /health and GET /metrics. When you replace the stand-in, keep this file, change it,
or write your own: only the behaviour has to stay (see docs/ARCHITECTURE.md, "Shared rules").
"""

import json
import logging
import re
import secrets
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated

from fastapi import FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class ApiError(Exception):
    """Raise this anywhere to answer with the shared error format."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(
    status_code: int, code: str, message: str, request_id: str, headers: dict | None = None
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def now_utc() -> datetime:
    return datetime.now(UTC)


def iso(moment: datetime) -> str:
    """ISO 8601 in UTC, e.g. 2026-11-14T09:30:00Z."""
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def current_user(x_user_id: Annotated[str | None, Header(max_length=128)] = None) -> str:
    """The gateway sets X-User-Id after checking the login token. No header means not logged in."""
    if not x_user_id:
        raise ApiError(401, "NOT_AUTHENTICATED", "Missing X-User-Id (requests must come through the gateway)")
    return x_user_id


class JsonFormatter(logging.Formatter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "timestamp": iso(now_utc()),
            "service": self.service_name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for field in ("request_id", "method", "path", "status", "duration_ms", "job_id"):
            if hasattr(record, field):
                line[field] = getattr(record, field)
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line)


HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}


def allowed_methods(app, path: str) -> str:
    """All methods this service documents for `path`, e.g. "GET, POST" (the Allow header of a 405).

    Read from the service's own OpenAPI description (the same one served at /openapi.json).
    """
    methods = set()
    for template, operations in app.openapi()["paths"].items():
        # "/projects/{project_id}" -> a pattern where {project_id} matches one path segment
        pattern = re.sub(r"\\\{[^}]*\\\}", "[^/]+", re.escape(template))
        if re.fullmatch(pattern, path):
            methods |= {name.upper() for name in operations if name in HTTP_METHODS}
    return ", ".join(sorted(methods))


_METRICS: dict[str, tuple[Counter, Histogram]] = {}


def _metrics(service_name: str) -> tuple[Counter, Histogram]:
    """Prometheus metrics may be created only once per process (the tests build several apps)."""
    if service_name not in _METRICS:
        prefix = service_name.replace("-", "_")
        _METRICS[service_name] = (
            Counter(f"{prefix}_requests_total", "Requests handled", ["method", "endpoint", "status"]),
            Histogram(f"{prefix}_request_duration_seconds", "Time to answer", ["endpoint"]),
        )
    return _METRICS[service_name]


def setup_service(
    app: FastAPI, service_name: str, is_ready: Callable[[], bool] = lambda: True
) -> logging.Logger:
    """Add the shared rules to `app`. `is_ready` decides whether /health answers 200 or 503."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service_name))
    logger = logging.getLogger(service_name)
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    requests_total, duration = _metrics(service_name)

    def request_id_of(request: Request) -> str:
        return getattr(request.state, "request_id", "unknown")

    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return error_response(error.status_code, error.code, error.message, request_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()))
        return error_response(
            422, "VALIDATION_FAILED", f"{where}: {first.get('msg', 'invalid')}", request_id_of(request)
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(error.status_code, "HTTP_ERROR")
        headers = dict(error.headers or {})
        if error.status_code == 405:  # HTTP requires listing the methods that ARE allowed
            headers["Allow"] = allowed_methods(request.app, request.url.path)
        return error_response(
            error.status_code, code, str(error.detail), request_id_of(request), headers=headers
        )

    async def request_context(request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if SAFE_REQUEST_ID.match(incoming) else f"req-{secrets.token_hex(4)}"
        request.state.request_id = request_id
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unexpected error", extra={"request_id": request_id})
            response = error_response(
                500, "INTERNAL_ERROR", f"Unexpected error in {service_name}", request_id
            )
        seconds = time.perf_counter() - started
        response.headers["X-Request-Id"] = request_id
        endpoint = getattr(request.scope.get("route"), "path", "unmatched")
        requests_total.labels(request.method, endpoint, str(response.status_code)).inc()
        duration.labels(endpoint).observe(seconds)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(seconds * 1000, 1),
            },
        )
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=request_context)

    @app.get("/health")
    def health(request: Request) -> JSONResponse:
        if not is_ready():
            return error_response(
                503, "SERVICE_UNAVAILABLE", f"{service_name} is not ready", request_id_of(request)
            )
        return JSONResponse({"status": "ok", "service": service_name})

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return logger
