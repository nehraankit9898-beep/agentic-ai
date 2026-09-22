from .base import BaseTool
import os
from pathlib import Path


class DateTimeTool(BaseTool):
    """Tool for getting current date and time information."""

    name = "date_time"
    description = "Get the current date, time, or day of the week"
    input_schema = {
        "type": "object",
        "properties": {
            "format": {
                "type": "string",
                "description": "What to return: 'date', 'time', 'datetime', 'day'",
                "enum": ["date", "time", "datetime", "day"],
            }
        },
        "required": [],
    }

    async def execute(self, format: str = "datetime") -> dict:
        """
        Get current date/time information.

        Args:
            format: Type of information to return

        Returns:
            Dict with date/time information
        """
        from datetime import datetime

        try:
            now = datetime.now()

            if format == "date":
                result = now.strftime("%Y-%m-%d")
            elif format == "time":
                result = now.strftime("%H:%M:%S")
            elif format == "day":
                result = now.strftime("%A")
            else:  # datetime
                result = now.strftime("%Y-%m-%d %H:%M:%S")

            return {
                "success": True,
                "result": result,
                "format": format,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error getting date/time: {str(e)}",
            }
