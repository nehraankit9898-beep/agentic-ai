import json
import urllib.parse
import urllib.request

from .base import BaseTool
from ..core.config import settings


USER_AGENT = "AgenticAIAssistant/0.1 (personal agent; +http://localhost)"


class WebSearchTool(BaseTool):
    """Configurable web search tool.

    Provider selection via WEB_SEARCH_PROVIDER env var:
      - "duckduckgo" (default): keyless HTML endpoint, works out of the box
      - "serper": needs SERPER_API_KEY (paid API, optional)

    External network access is disabled by default (allow_web_access=False)
    per the project safety rules; enable it explicitly in .env.
    """

    name = "web_search"
    description = (
        "Search the web for information. Returns a list of results with "
        "title, url and snippet. Use for current events, facts, or research."
    )
    requires_confirmation = True  # external requests need explicit user consent

    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results (1-10)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    output_schema = {
        "type": "object",
        "properties": {
            "success": {"type": "boolean"},
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "snippet": {"type": "string"},
                    },
                },
            },
            "provider": {"type": "string"},
            "error": {"type": "string"},
        },
    }

    def validate_input(self, **kwargs) -> tuple[bool, str | None]:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            return False, "Input 'query' must be a non-empty string"
        max_results = kwargs.get("max_results", 5)
        if not isinstance(max_results, int) or not 1 <= max_results <= 10:
            return False, "'max_results' must be an integer between 1 and 10"
        return True, None

    async def execute(self, query: str, max_results: int = 5) -> dict:
        if not settings.allow_web_access:
            return {
                "success": False,
                "error": (
                    "Web access is disabled for safety. Set ALLOW_WEB_ACCESS=true "
                    "in backend/.env and restart the server to enable web_search."
                ),
            }

        provider = settings.web_search_provider.lower()
        try:
            if provider == "serper":
                return await self._search_serper(query, max_results)
            return await self._search_duckduckgo(query, max_results)
        except Exception as e:
            return {"success": False, "error": f"Search failed ({provider}): {e}"}

    async def _search_duckduckgo(self, query: str, max_results: int) -> dict:
        """Keyless search via DuckDuckGo's html endpoint (stdlib only)."""
        url = "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(
            {"q": query, "kl": "wt-wt"}
        )
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=settings.web_timeout_seconds) as resp:
            html = resp.read().decode("utf-8", errors="replace")

        results = self._parse_ddg_html(html, max_results)
        return {
            "success": True,
            "provider": "duckduckgo",
            "query": query,
            "results": results,
        }

    @staticmethod
    def _parse_ddg_html(html: str, max_results: int) -> list[dict]:
        """Parse result blocks from DDG html endpoint without extra deps."""
        import re
        from html import unescape

        results: list[dict] = []
        blocks = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>'
            r'(?:.*?<a[^>]+class="result__snippet"[^>]*>(.*?)</a>)?',
            html,
            re.DOTALL,
        )
        for href, title, snippet in blocks:
            link = unescape(href)
            # DDG wraps URLs in a redirect: //duckduckgo.com/l/?uddg=<encoded>
            if "uddg=" in link:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                link = qs.get("uddg", [link])[0]
            clean_title = unescape(re.sub(r"<[^>]+>", "", title)).strip()
            clean_snippet = unescape(re.sub(r"<[^>]+>", "", snippet or "")).strip()
            if clean_title:
                results.append(
                    {"title": clean_title, "url": link, "snippet": clean_snippet}
                )
            if len(results) >= max_results:
                break
        return results

    async def _search_serper(self, query: str, max_results: int) -> dict:
        """Serper.dev JSON API (requires SERPER_API_KEY, never sent to the LLM)."""
        api_key = settings.serper_api_key
        if not api_key or api_key == "your-serper-key-here":
            return {
                "success": False,
                "error": "SERPER_API_KEY is not configured. Use provider 'duckduckgo' or set a key in .env.",
            }
        payload = json.dumps({"q": query, "num": max_results}).encode()
        req = urllib.request.Request(
            "https://google.serper.dev/search",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-KEY": api_key,  # kept server-side only
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=settings.web_timeout_seconds) as resp:
            data = json.loads(resp.read().decode())

        results = [
            {
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", ""),
            }
            for item in data.get("organic", [])[:max_results]
        ]
        return {"success": True, "provider": "serper", "query": query, "results": results}
