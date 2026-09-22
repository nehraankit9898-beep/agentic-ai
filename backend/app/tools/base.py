from abc import ABC, abstractmethod
from typing import Any, Optional
from pydantic import BaseModel


class BaseTool(ABC):
    """Abstract base class for all tools."""

    name: str = "base_tool"
    description: str = "Base tool description"
    input_schema: dict = {}
    requires_confirmation: bool = False

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """Execute the tool with given arguments."""
        pass

    def validate_input(self, **kwargs) -> tuple[bool, Optional[str]]:
        """Validate input arguments against schema."""
        # Basic validation - can be overridden by subclasses
        return True, None

    def get_definition(self) -> dict:
        """Get the tool definition for the LLM."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "requires_confirmation": self.requires_confirmation,
        }
