"""The shared error format (contracts/error-format.json), used for every non-2xx answer."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    return JSONResponse(status_code=status_code, content=body)


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# Names for the HTTP errors FastAPI raises by itself.
STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "NOT_AUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_FAILED",
    429: "TOO_MANY_REQUESTS",
    503: "SERVICE_UNAVAILABLE",
}


def install_error_handlers(app: FastAPI) -> None:
    """Make FastAPI's own errors use the shared format too."""

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(error.status_code, "HTTP_ERROR")
        return error_response(error.status_code, code, str(error.detail), request_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(
            422, "VALIDATION_FAILED", "Request does not match the contract", request_id_of(request)
        )
