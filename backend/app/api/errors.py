"""Phase 1 – standard error model & helpers.

Every API error response follows:

    {
      "success": false,
      "error": {"code": "TOOL_EXECUTION_FAILED", "message": "..."},
      "request_id": "..."
    }
"""

import uuid
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.logging import get_logger, request_id_var

logger = get_logger("app.api.errors")


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    request_id: str = Field(default_factory=new_request_id)

    @classmethod
    def make(cls, code: str, message: str, request_id: Optional[str] = None) -> "ErrorResponse":
        return cls(
            error=ErrorDetail(code=code, message=message),
            request_id=request_id or new_request_id(),
        )


class AppError(HTTPException):
    """Application error carrying a machine-readable code."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        super().__init__(status_code=status_code, detail=message)


def error_response(
    request: Request,
    code: str,
    message: str,
    status_code: int = 500,
) -> JSONResponse:
    rid = getattr(request.state, "request_id", None) or request_id_var.get() or new_request_id()
    payload: dict[str, Any] = ErrorResponse.make(code, message, rid).model_dump()
    return JSONResponse(status_code=status_code, content=payload)


def register_error_handlers(app: FastAPI) -> None:
    """Install handlers so ALL API errors use the standard envelope.

    Standard shape:
        {"success": false, "error": {"code": ..., "message": ...}, "request_id": ...}
    """

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("x-request-id") or new_request_id()
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        logger.warning(
            "api_error",
            extra={"event_data": {"code": exc.code, "status": exc.status_code}},
        )
        return error_response(request, exc.code, exc.detail, exc.status_code)

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        return error_response(request, "HTTP_ERROR", str(exc.detail), exc.status_code)

    @app.exception_handler(Exception)
    async def unhandled_exc_handler(request: Request, exc: Exception):
        logger.exception("unhandled_error")
        # Do not leak internal exception details to clients in production.
        message = str(exc) if getattr(request.app.state, "debug", True) else "Internal server error"
        return error_response(request, "INTERNAL_ERROR", message, 500)
