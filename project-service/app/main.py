"""Build the Projects service app. Run with:  uvicorn --factory app.main:create_app --port 8001"""

import os
import re
import secrets
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.errors import error_response, install_error_handlers
from app.logs import SERVICE_NAME, setup_logging
from app.metrics import DURATION, REQUESTS
from app.routes import router

SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def create_app(engine: Engine | None = None) -> FastAPI:
    """`engine` lets the tests use their own database; normally it comes from DATABASE_URL."""
    engine = engine or create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    logger = setup_logging(os.environ.get("LOG_LEVEL", "INFO"))

    app = FastAPI(title="CloudTrain Projects service", version="1.0.0")
    app.state.sessions = sessionmaker(engine, expire_on_commit=False)
    install_error_handlers(app)
    app.include_router(router)

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
                500, "INTERNAL_ERROR", "Unexpected error in the Projects service", request_id
            )
        duration = time.perf_counter() - started
        response.headers["X-Request-Id"] = request_id

        # The endpoint's pattern (e.g. /projects/{project_id}), so metrics do not explode per project.
        route = request.scope.get("route")
        endpoint = getattr(route, "path", "unmatched")
        REQUESTS.labels(request.method, endpoint, str(response.status_code)).inc()
        DURATION.labels(endpoint).observe(duration)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 1),
            },
        )
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=request_context)

    @app.get("/health")
    def health(request: Request) -> Response:
        """Ready only when the database answers."""
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            return error_response(
                503, "SERVICE_UNAVAILABLE", "The database is not reachable", request.state.request_id
            )
        return JSONResponse({"status": "ok", "service": SERVICE_NAME})

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
