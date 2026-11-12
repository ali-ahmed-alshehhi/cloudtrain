"""Build the gateway app. Run with:  uvicorn --factory app.main:create_app --port 5810

Order of work for every forwarded request:
  1. give it a request ID (keep the caller's one, or make a new one)
  2. refuse /internal/ paths (404)
  3. find its route in routes.yaml (404 if none) and check the method (405)
  4. check the login token (401)
  5. forward it with X-User-Id and X-Request-Id (503 if the service is down or slow)
  6. write one JSON log line and update the metrics
"""

import re
import secrets
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app import auth, proxy
from app.config import Settings, load_settings
from app.errors import error_response, install_error_handlers
from app.logs import SERVICE_NAME, setup_logging
from app.metrics import DURATION, REQUESTS
from app.routing import find_route, is_forbidden_path, load_routes

ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
# A caller's request ID is kept only if it is short and plain, so it cannot break the logs.
SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def new_request_id() -> str:
    return f"req-{secrets.token_hex(4)}"


def create_app(
    settings: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None
) -> FastAPI:
    """`transport` lets the tests replace the real network with fake services."""
    settings = settings or load_settings()
    routes = load_routes()
    logger = setup_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # One shared HTTP client for all forwarded requests (reuses connections).
        app.state.http = httpx.AsyncClient(transport=transport)
        yield
        await app.state.http.aclose()

    app = FastAPI(title="CloudTrain API Gateway", version="1.0.0", lifespan=lifespan)
    install_error_handlers(app)

    async def request_context(request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if SAFE_REQUEST_ID.match(incoming) else new_request_id()
        request.state.request_id = request_id
        request.state.route_name = "gateway"
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("unexpected error", extra={"request_id": request_id})
            response = error_response(500, "INTERNAL_ERROR", "Unexpected error in the gateway", request_id)
        duration = time.perf_counter() - started
        response.headers["X-Request-Id"] = request_id

        route_name = request.state.route_name
        REQUESTS.labels(route_name, request.method, str(response.status_code)).inc()
        DURATION.labels(route_name).observe(duration)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "route": route_name,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 1),
            },
        )
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=request_context)
    # Added last, so it runs first: answers the browser's CORS checks before anything else.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "service": SERVICE_NAME}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.api_route("/{path:path}", methods=ALL_METHODS, include_in_schema=False)
    async def forward(request: Request) -> Response:
        request_id = request.state.request_id
        path = request.url.path

        if path in ("/health", "/metrics"):  # the gateway's own endpoints are GET only
            return error_response(
                405,
                "METHOD_NOT_ALLOWED",
                f"{request.method} is not allowed on {path}",
                request_id,
                headers={"Allow": "GET"},
            )

        if is_forbidden_path(path):
            return error_response(404, "NOT_FOUND", f"No route for {path}", request_id)

        route = find_route(routes, path)
        if route is None:
            return error_response(404, "NOT_FOUND", f"No route for {path}", request_id)
        request.state.route_name = route.name
        if not route.allows(request.method, path):
            return error_response(
                405,
                "METHOD_NOT_ALLOWED",
                f"{request.method} is not allowed on {path}",
                request_id,
                headers={"Allow": route.allowed_methods(path)},
            )

        try:
            token = auth.bearer_token(request.headers.get("authorization"))
            user_id = auth.verify_token(token, settings)
        except auth.AuthError as error:
            return error_response(401, "NOT_AUTHENTICATED", str(error), request_id)

        is_upload = request.headers.get("content-type", "").startswith("multipart/")
        timeout = settings.upload_timeout_seconds if is_upload else settings.timeout_seconds
        return await proxy.forward(app.state.http, request, route, user_id, request_id, timeout)

    return app
