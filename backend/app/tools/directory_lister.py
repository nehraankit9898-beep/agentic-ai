from .base import BaseTool
from pathlib import Path

from ..core.config import settings
from ..core.security import safe_join, SecurityError


class DirectoryListerTool(BaseTool):
    """Tool for listing directory contents."""

    name = "directory_lister"
    description = "List files and directories in a given path"
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Directory path to list (default: current directory)",
            },
            "show_hidden": {
                "type": "boolean",
                "description": "Whether to show hidden files (default: false)",
                "default": False,
            },
        },
        "required": [],
    }

    async def execute(self, path: str = ".", show_hidden: bool = False) -> dict:
        """
        List directory contents.

        Args:
            path: Directory path to list
            show_hidden: Whether to show hidden files

        Returns:
            Dict with directory listing
        """
        try:
            # Security: canonical-path validation keeps listings inside the
            # configured WORKSPACE_ROOT.
            base_dir = settings.workspace_path
            try:
                target_path = safe_join(base_dir, path)
            except SecurityError as e:
                return {"success": False, "error": f"Access denied: {e.message}"}

            if not target_path.exists():
                return {
                    "success": False,
                    "error": f"Path not found: {path}",
                }

            if not target_path.is_dir():
                return {
                    "success": False,
                    "error": f"Not a directory: {path}",
                }

            # List directory contents
            items = []
            for item in sorted(target_path.iterdir()):
                # Skip hidden files unless requested
                if not show_hidden and item.name.startswith("."):
                    continue

                item_type = "directory" if item.is_dir() else "file"
                items.append(
                    {
                        "name": item.name,
                        "type": item_type,
                        "path": str(item),
                    }
                )

            return {
                "success": True,
                "directory": str(target_path),
                "items": items,
                "total_count": len(items),
            }

        except PermissionError:
            return {
                "success": False,
                "error": f"Permission denied: {path}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error listing directory: {str(e)}",
            }
