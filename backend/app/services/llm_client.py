import json
from typing import Any, AsyncGenerator, Optional

import httpx

from ..models.schemas import Message, MessageRole
from ..core.config import settings


def _extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of the first JSON object in *text*."""
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        try:
            return json.loads(text[start:end])
        except (ValueError, TypeError):
            return None
    return None


class OpenAICompatClient:
    """Minimal async client for any OpenAI-compatible /v1/chat/completions API.

    Used as the cloud fallback provider (OpenAI, Groq, Together, ...). The
    API key is kept server-side only and never reaches the agent or tools.
    """

    def __init__(self):
        self.base_url = (settings.openai_base_url or "https://api.openai.com/v1").rstrip("/")
        self.model = settings.openai_model or "gpt-4o-mini"
        self.api_key = settings.openai_api_key
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=120.0,
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
        return self._client

    @staticmethod
    def _payload(messages: list[dict], stream: bool, tools: Optional[list[dict]] = None) -> dict:
        payload: dict[str, Any] = {"model": "", "messages": messages, "stream": stream}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        return payload

    async def chat(self, messages: list[dict], stream: bool = False) -> str:
        client = await self._get_client()
        payload = {"model": self.model, "messages": messages}
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"] or ""

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> tuple[str, list[dict]]:
        """Native function calling. Returns (content, normalized_tool_calls)."""
        client = await self._get_client()
        oa_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("input_schema")
                    or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": oa_tools,
            "tool_choice": "auto",
        }
        resp = await client.post("/chat/completions", json=payload)
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        calls = []
        for tc in msg.get("tool_calls") or []:
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except ValueError:
                args = {}
            calls.append(
                {"id": tc.get("id"), "name": tc["function"]["name"], "arguments": args}
            )
        return msg.get("content") or "", calls

    async def check_health(self) -> bool:
        return bool(self.api_key)

    async def aclose(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def close(self):
        if self._client and not self._client.is_closed:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._client.aclose())
            else:
                asyncio.run(self._client.aclose())


class LLMClient:
    """Client for interacting with LLM providers (Ollama by default)."""

    def __init__(self):
        self.base_url = settings.effective_ollama_url
        self.model = settings.effective_ollama_model
        self.provider = settings.llm_provider
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=120.0,
            )
        return self._client

    async def chat(
        self,
        messages: list[dict],
        stream: bool = False,
    ) -> str:
        """
        Send a chat request to the LLM and get a response.

        Args:
            messages: List of message dicts with 'role' and 'content'
            stream: Whether to stream the response

        Returns:
            The assistant's response text
        """
        client = await self._get_client()

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
        }

        try:
            if stream:
                return await self._stream_response(client, payload)
            else:
                response = await client.post("/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("message", {}).get("content", "")
        except httpx.HTTPError as e:
            raise RuntimeError(f"LLM request failed: {str(e)}")

    async def _stream_response(
        self, client: httpx.AsyncClient, payload: dict
    ) -> str:
        """Handle streaming response from LLM."""
        full_response = ""
        async with client.stream("POST", "/api/chat", json=payload) as response:
            async for line in response.aiter_lines():
                if line.strip():
                    import json

                    try:
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        full_response += chunk
                    except json.JSONDecodeError:
                        continue
        return full_response

    async def chat_stream(
        self, messages: list[dict]
    ) -> AsyncGenerator[str, None]:
        """Yield response chunks as the model generates them (NDJSON stream)."""
        client = await self._get_client()
        payload = {"model": self.model, "messages": messages, "stream": True}
        async with client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                chunk = data.get("message", {}).get("content", "")
                if chunk:
                    yield chunk

    async def chat_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> tuple[str, list[dict]]:
        """Native ReAct-style tool calling via Ollama's /api/chat `tools` field.

        Args:
            messages: Conversation messages (OpenAI-style dicts)
            tools: Tool definitions from ToolManager.list_tools()

        Returns:
            Tuple of (response_text, normalized_tool_calls) where each call is
            {"id", "name", "arguments"}.
        """
        ollama_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t.get("input_schema")
                    or {"type": "object", "properties": {}},
                },
            }
            for t in tools
        ]
        payload = {
            "model": self.model,
            "messages": messages,
            "tools": ollama_tools,
            "stream": False,
        }
        client = await self._get_client()
        resp = await client.post("/api/chat", json=payload)
        resp.raise_for_status()
        msg = resp.json().get("message", {})
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function", {})
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                args = _extract_json(args) or {}
            calls.append(
                {"id": tc.get("id"), "name": fn.get("name", ""), "arguments": args}
            )
        return msg.get("content") or "", calls

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> tuple[str, list[dict]]:
        """Backward-compatible alias for chat_with_tools."""
        return await self.chat_with_tools(messages, tools)

    async def check_health(self) -> bool:
        """Check if the LLM service is available."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    async def aclose(self):
        """Close the underlying async HTTP client (awaitable)."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def close(self):
        """Synchronous best-effort close (kept for backward compatibility).

        Prefer ``await aclose()``; calling this from within a running event
        loop schedules the proper async close.
        """
        if self._client and not self._client.is_closed:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None:
                loop.create_task(self._client.aclose())
            else:
                # No loop running: safe to drive the coroutine to completion.
                asyncio.run(self._client.aclose())
