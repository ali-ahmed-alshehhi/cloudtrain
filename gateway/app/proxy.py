"""Forward one request to a service and pass its answer back.

The request body and the answer are streamed, so a large dataset upload or download is never
held in memory all at once.
"""

import json

import httpx
from fastapi import Request
from starlette.background import BackgroundTask
from starlette.responses import Response, StreamingResponse

from app.errors import error_response
from app.routing import Route

# Headers that only describe one network hop and must not be copied to the next one.
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "host",
}
# Headers the client may NOT send through: the gateway sets these itself.
SET_BY_GATEWAY = {"authorization", "x-user-id", "x-request-id"}


def outgoing_headers(request: Request, user_id: str, request_id: str) -> dict[str, str]:
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP | SET_BY_GATEWAY
    }
    headers["X-User-Id"] = user_id
    headers["X-Request-Id"] = request_id
    return headers


def has_body(request: Request) -> bool:
    return "content-length" in request.headers or "transfer-encoding" in request.headers


async def forward(
    client: httpx.AsyncClient,
    request: Request,
    route: Route,
    user_id: str,
    request_id: str,
    timeout_seconds: float,
) -> Response:
    url = route.upstream_url(request.url.path, request.url.query)
    upstream_request = client.build_request(
        request.method,
        url,
        headers=outgoing_headers(request, user_id, request_id),
        content=request.stream() if has_body(request) else None,
        timeout=httpx.Timeout(timeout_seconds),
    )
    try:
        upstream = await client.send(upstream_request, stream=True)
    except httpx.TimeoutException:
        return error_response(503, "SERVICE_UNAVAILABLE", f"{route.name} did not answer in time", request_id)
    except httpx.TransportError:
        return error_response(503, "SERVICE_UNAVAILABLE", f"{route.name} is not reachable", request_id)

    if route.errors_from == "mlflow" and upstream.status_code >= 400:
        return await mlflow_error(upstream, request_id)

    answer_headers = {
        name: value for name, value in upstream.headers.items() if name.lower() not in HOP_BY_HOP
    }
    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        headers=answer_headers,
        background=BackgroundTask(upstream.aclose),
    )


async def mlflow_error(upstream: httpx.Response, request_id: str) -> Response:
    """MLflow answers errors as {"error_code": ..., "message": ...}; turn that into our format."""
    body = await upstream.aread()
    await upstream.aclose()
    try:
        details = json.loads(body)
        code = str(details.get("error_code") or "MLFLOW_ERROR")
        message = str(details.get("message") or "MLflow returned an error")
    except (ValueError, AttributeError):
        code, message = "MLFLOW_ERROR", "MLflow returned an error"
    return error_response(upstream.status_code, code, message, request_id)
