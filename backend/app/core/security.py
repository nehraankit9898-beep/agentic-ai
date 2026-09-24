"""Phase 1 – security helpers.

- API key verification (constant-time compare)
- Path traversal protection for workspace-bound file access
"""

import hmac
import os
from pathlib import Path

from app.core.config import settings


class SecurityError(Exception):
    """Raised when a security check fails."""

    def __init__(self, code: str = "FORBIDDEN", message: str = "Forbidden"):
        self.code = code
        self.message = message
        super().__init__(message)


def verify_api_key(provided_key: str | None) -> bool:
    """Constant-time comparison of the provided API key with the configured one."""
    if not provided_key:
        return False
    return hmac.compare_digest(provided_key.encode(), settings.api_key.encode())


def safe_join(base_dir: Path, user_path: str) -> Path:
    """Join *user_path* onto *base_dir*, refusing path-traversal escapes.

    Returns the resolved absolute path; raises SecurityError if the result
    would fall outside *base_dir*.
    """
    base = Path(base_dir).resolve()
    candidate = (base / user_path).resolve()
    if not str(candidate).startswith(str(base) + os.sep) and candidate != base:
        raise SecurityError(
            code="PATH_TRAVERSAL_BLOCKED",
            message=f"Path '{user_path}' escapes the allowed workspace root.",
        )
    return candidate
