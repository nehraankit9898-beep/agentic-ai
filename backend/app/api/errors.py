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

from fastapi import HTTPException, Request
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
