"""Phase 1 – structured logging with request/session correlation fields.

Every log record can carry contextual fields:
    request_id, session_id, user_id, agent_run_id, tool_name, duration, status, error

Usage:
    from app.core.logging import configure_logging, get_logger, log_event

    log(logger, "tool_call", tool_name="calculator", duration_ms=12.3, status="ok")
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional

# Correlation context (set per-request by middleware / agent runtime)
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
session_id_var: ContextVar[Optional[str]] = ContextVar("session_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
agent_run_id_var: ContextVar[Optional[str]] = ContextVar("agent_run_id", default=None)


class JsonFormatter(logging.Formatter):
    """Minimal JSON line formatter including correlation context."""

    CORRELATION_FIELDS = {
        "request_id": request_id_var,
        "session_id": session_id_var,
        "user_id": user_id_var,
        "agent_run_id": agent_run_id_var,
    }

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, var in self.CORRELATION_FIELDS.items():
            value = var.get()
            if value is not None:
                payload[key] = value
        # extra fields attached via `extra={"event_data": {...}}`
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            payload.update(event_data)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_configured = False


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once (idempotent)."""
    global _configured
    if _configured:
        logging.getLogger().setLevel(level.upper())
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    _configured = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(
    logger: logging.Logger,
    event: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured event: tool_name, duration, status, error, etc."""
    logger.log(level, event, extra={"event_data": {"event": event, **fields}})
