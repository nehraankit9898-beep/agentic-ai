import httpx
from typing import Optional, AsyncGenerator
from ..models.schemas import Message, MessageRole
from ..core.config import settings


class LLMClient:
    """Client for interacting with LLM providers (Ollama by default)."""

    def __init__(self):
        self.base_url = settings.llm_base_url
        self.model = settings.llm_model
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

    async def generate_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> tuple[str, list[dict]]:
        """
        Generate a response with tool calling support.

        Args:
            messages: Conversation messages
            tools: List of tool definitions

        Returns:
            Tuple of (response_text, list_of_tool_calls)
        """
        # For Ollama, we'll use a simple prompt-based approach for tool calling
        # In production, you might want to use a model with native tool support

        system_prompt = """You are an AI assistant that can use tools to help users.
When you need to use a tool, respond with this format:

THOUGHT: [Your reasoning about what to do]
ACTION: [tool_name]
ACTION_INPUT: {"arg1": "value1", "arg2": "value2"}

If no tool is needed, just respond normally.

Available tools:
"""

        for tool in tools:
            system_prompt += f"\n- {tool['name']}: {tool['description']}"
            system_prompt += f"\n  Input schema: {tool.get('input_schema', {})}"

        # Add system prompt to messages
        enhanced_messages = [
            {"role": "system", "content": system_prompt},
            *messages,
        ]

        response = await self.chat(enhanced_messages)
        return response, []  # Tool parsing will be done separately

    async def check_health(self) -> bool:
        """Check if the LLM service is available."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            return response.status_code == 200
        except Exception:
            return False

    def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            self._client.close()
