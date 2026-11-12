"""The shared error format (contracts/error-format.json), used for every non-2xx answer."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    """Raise this anywhere to answer with the shared error format."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_response(status_code: int, code: str, message: str, request_id: str) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "request_id": request_id}}
    return JSONResponse(status_code=status_code, content=body)


def request_id_of(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


# Names for the HTTP errors FastAPI raises by itself (e.g. an unknown path).
STATUS_CODES = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return error_response(error.status_code, error.code, error.message, request_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        first = error.errors()[0] if error.errors() else {}
        where = ".".join(str(part) for part in first.get("loc", ()))
        message = (
            f"{where}: {first.get('msg', 'invalid')}" if where else "Request does not match the contract"
        )
        return error_response(422, "VALIDATION_FAILED", message, request_id_of(request))

    @app.exception_handler(OperationalError)
    async def database_down(request: Request, error: OperationalError) -> JSONResponse:
        return error_response(
            503, "SERVICE_UNAVAILABLE", "The database is not reachable", request_id_of(request)
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = STATUS_CODES.get(error.status_code, "HTTP_ERROR")
        return error_response(error.status_code, code, str(error.detail), request_id_of(request))
