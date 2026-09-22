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

        self.register_tool(CalculatorTool())
        self.register_tool(DateTimeTool())
        self.register_tool(FileReaderTool())
        self.register_tool(FileWriterTool())
        self.register_tool(DirectoryListerTool())

    def register_tool(self, tool: BaseTool) -> None:
        """Register a tool for use."""
        if tool.name in settings.allowed_tools or settings.allowed_tools == ["*"]:
            self._tools[tool.name] = tool

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        """Get definitions of all registered tools."""
        return [tool.get_definition() for tool in self._tools.values()]

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed by configuration."""
        return tool_name in settings.allowed_tools or settings.allowed_tools == ["*"]

    async def execute_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Execute a tool with given arguments.

        Args:
            tool_name: Name of the tool to execute
            **kwargs: Arguments to pass to the tool

        Returns:
            Tool execution result
        """
        tool = self.get_tool(tool_name)

        if tool is None:
            return {
                "success": False,
                "error": f"Tool not found: {tool_name}",
            }

        # Validate input
        is_valid, error_msg = tool.validate_input(**kwargs)
        if not is_valid:
            return {
                "success": False,
                "error": error_msg or "Invalid input",
            }

        try:
            result = await tool.execute(**kwargs)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"Tool execution failed: {str(e)}",
            }

    def requires_confirmation(self, tool_name: str) -> bool:
        """Check if a tool requires user confirmation."""
        tool = self.get_tool(tool_name)
        if tool:
            return tool.requires_confirmation
        return False
