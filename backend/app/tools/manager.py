from typing import Optional

from .base import BaseTool
from ..core.config import settings


class ToolManager:
    """Manages registration and execution of tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._initialize_default_tools()

    def _initialize_default_tools(self):
        """Register default tools."""
        from .calculator import CalculatorTool
        from .date_time import DateTimeTool
        from .file_reader import FileReaderTool
        from .file_writer import FileWriterTool
        from .directory_lister import DirectoryListerTool
        from .python_executor import PythonExecutorTool
        from .web_search import WebSearchTool
        from .http_fetcher import HttpFetcherTool
        from .text_processor import TextProcessorTool
        from .memory_store import MemoryStoreTool

        for tool in (
            CalculatorTool(),
            DateTimeTool(),
            FileReaderTool(),
            FileWriterTool(),
            DirectoryListerTool(),
            PythonExecutorTool(),
            WebSearchTool(),
            HttpFetcherTool(),
            TextProcessorTool(),
            MemoryStoreTool(),
        ):
            self.register_tool(tool)

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool for use (only if allowed by configuration)."""
        if self.is_tool_allowed(tool.name):
            self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """Get definitions of all registered tools."""
        return [tool.get_definition() for tool in self._tools.values()]

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed by configuration.

        Supports both list-style (ALLOWED_TOOLS=a,b,c) and wildcard "*" values.
        """
        allowed = settings.allowed_tools
        if allowed == ["*"] or allowed == "*":
            return True
        # Normalize in case the value came through as a single comma string.
        if isinstance(allowed, str):
            names = [n.strip() for n in allowed.split(",")]
        else:
            names = list(allowed)
        return tool_name in names

    async def execute_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Execute a tool with given arguments.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments to pass to the tool

        Returns:
            Tool execution result. For successful runs the payload is also
            normalized with an "output" key (a compact text rendering of the
            result) so downstream consumers — including the LLM's final
            response step — always have something meaningful to read.
        """
        # Defense-in-depth: re-check the allowlist at execution time so a
        # tool can never run if it was removed from (or never added to)
        # settings.allowed_tools, even if it somehow ended up registered.
        if not self.is_tool_allowed(tool_name):
            return {
                "success": False,
                "error": f"Tool not allowed by configuration: {tool_name}",
            }

        tool = self.get_tool(tool_name)

        if tool is None:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
            }

        # Validate input
        try:
            is_valid, error_msg = tool.validate_input(**kwargs)
        except TypeError as e:
            # LLM produced malformed call signature (missing/unexpected args)
            return {
                "success": False,
                "error": f"Invalid arguments for tool '{tool_name}': {e}",
            }
        if not is_valid:
            return {
                "success": False,
                "error": error_msg or "Invalid input",
            }

        import asyncio
        import time

        from ..core.logging import get_logger, log_event

        logger = get_logger("app.tools")
        started = time.monotonic()
        status = "ok"
        error_text: str | None = None
        try:
            # Enforce MAX_TOOL_RUNTIME per tool invocation so a hanging tool
            # cannot block the event loop / agent run forever.
            result = await asyncio.wait_for(
                tool.execute(**kwargs), timeout=settings.max_tool_runtime
            )
            if isinstance(result, dict) and not result.get("success", True):
                status = "error"
                error_text = str(result.get("error", ""))[:500]
            if isinstance(result, dict) and result.get("success", True) and "output" not in result:
                result = {**result, "output": self._render_output(tool_name, result)}
            return result
        except asyncio.TimeoutError:
            status = "timeout"
            error_text = f"Tool '{tool_name}' exceeded {settings.max_tool_runtime}s runtime limit"
            return {"success": False, "error": error_text}
        except Exception as e:
            status = "error"
            error_text = str(e)[:500]
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
            }
        finally:
            log_event(
                logger,
                "tool_call",
                tool_name=tool_name,
                duration_ms=round((time.monotonic() - started) * 1000, 2),
                status=status,
                error=error_text,
            )

    @staticmethod
    def _render_output(tool_name: str, result: dict) -> str:
        """Compact text rendering of a successful tool payload (for LLM context)."""
        import json as _json

        payload = {k: v for k, v in result.items() if k != "success"}
        try:
            text = _json.dumps(payload, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(payload)
        return text[:4000]

    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation."""
        tool = self.get_tool(tool_name)
        if tool:
            return tool.requires_confirmation
        return False
