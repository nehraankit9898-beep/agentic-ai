"""Advanced: safe HTTP GET tool for fetching pages/APIs the agent needs.

Security posture mirrors web_search:
  - gated behind ALLOW_WEB_ACCESS (off by default)
  - requires explicit user confirmation before running
  - only http/https schemes, size-capped response body, timeout enforced
"""

import re

import httpx

from .base import BaseTool
from ..core.config import settings


USER_AGENT = "AgenticAIAssistant/0.2 (personal agent; +http://localhost)"
MAX_BODY_BYTES = 512_000  # 512 KB cap on fetched content


class HttpFetcherTool(BaseTool):
    """Fetch a URL and return its (optionally tag-stripped) text content."""

    name = "http_fetcher"
    description = (
        "Fetch a web page or API endpoint via HTTP GET and return its text "
        "content. Use for reading documentation, APIs, or a specific URL "
        "found via web_search."
    )
    requires_confirmation = True  # external network access needs consent

    input_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Absolute http(s) URL to fetch"},
            "max_chars": {
                "type": "integer",
                "description": "Maximum characters of content to return (default 8000)",
                "default": 8000,
            },
            "raw": {
                "type": "boolean",
                "description": "If true, keep HTML tags; default strips them to plain text",
                "default": False,
            },
        },
        "required": ["url"],
    }

    _TAG_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
    _ANY_TAG_RE = re.compile(r"<[^>]+>")
    _WS_RE = re.compile(r"\n{3,}")

    def validate_input(self, **kwargs) -> tuple[bool, str | None]:
        url = kwargs.get("url")
        if not isinstance(url, str) or not url.strip():
            return False, "Input 'url' must be a non-empty string"
        if not url.lower().startswith(("http://", "https://")):
            return False, "Only http(s) URLs are allowed"
        max_chars = kwargs.get("max_chars", 8000)
        if not isinstance(max_chars, int) or not 100 <= max_chars <= 100_000:
            return False, "'max_chars' must be an integer between 100 and 100000"
        return True, None

    @classmethod
    def _html_to_text(cls, html: str) -> str:
        from html import unescape

        text = cls._TAG_RE.sub(" ", html)
        text = cls._ANY_TAG_RE.sub(" ", text)
        text = unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = cls._WS_RE.sub("\n\n", text)
        return text.strip()

    async def execute(self, url: str, max_chars: int = 8000, raw: bool = False) -> dict:
        if not settings.allow_web_access:
            return {
                "success": False,
                "error": (
                    "Web access is disabled for safety. Set ALLOW_WEB_ACCESS=true "
                    "in backend/.env and restart the server to enable http_fetcher."
                ),
            }

        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": USER_AGENT},
                timeout=settings.web_timeout_seconds,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                resp = await client.get(url)

            body = resp.text[:MAX_BODY_BYTES]
            content_type = resp.headers.get("content-type", "")
            if "html" in content_type.lower() and not raw:
                body = self._html_to_text(body)

            truncated = len(resp.text) > max_chars
            return {
                "success": True,
                "url": str(resp.url),
                "status_code": resp.status_code,
                "content_type": content_type,
                "content": body[:max_chars],
                "truncated": truncated,
            }
        except httpx.TimeoutException:
            return {"success": False, "error": f"Request timed out after {settings.web_timeout_seconds}s"}
        except httpx.HTTPError as e:
            return {"success": False, "error": f"HTTP request failed: {e}"}
        except Exception as e:  # noqa: BLE001 - surface a clean tool error
            return {"success": False, "error": f"Fetch failed: {e}"}
