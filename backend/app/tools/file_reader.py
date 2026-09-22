from .base import BaseTool
import os
from pathlib import Path


class FileReaderTool(BaseTool):
    """Tool for reading file contents."""

    name = "file_reader"
    description = "Read the contents of a text file"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to read",
            },
            "max_lines": {
                "type": "integer",
                "description": "Maximum number of lines to read (default: 100)",
                "default": 100,
            },
        },
        "required": ["file_path"],
    }
    requires_confirmation = True

    async def execute(self, file_path: str, max_lines: int = 100) -> dict:
        """
        Read contents of a file.

        Args:
            file_path: Path to the file
            max_lines: Maximum lines to read

        Returns:
            Dict with file contents or error
        """
        try:
            # Security: Prevent path traversal attacks
            base_dir = Path(os.getcwd())
            target_path = Path(file_path).resolve()

            # Ensure the path is within allowed directory
            try:
                target_path.relative_to(base_dir)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Access denied: File must be within {base_dir}",
                }

            if not target_path.exists():
                return {
                    "success": False,
                    "error": f"File not found: {file_path}",
                }

            if not target_path.is_file():
                return {
                    "success": False,
                    "error": f"Not a file: {file_path}",
                }

            # Check file size (limit to 1MB)
            if target_path.stat().st_size > 1024 * 1024:
                return {
                    "success": False,
                    "error": "File too large (max 1MB)",
                }

            # Read file content
            with open(target_path, "r", encoding="utf-8") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        lines.append(f"... ({max_lines} lines shown)")
                        break
                    lines.append(line.rstrip("\n"))

                content = "\n".join(lines)

            return {
                "success": True,
                "content": content,
                "file_path": str(target_path),
                "lines_read": min(len(lines), max_lines),
            }

        except PermissionError:
            return {
                "success": False,
                "error": f"Permission denied: {file_path}",
            }
        except UnicodeDecodeError:
            return {
                "success": False,
                "error": "Cannot read binary file. Only text files supported.",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error reading file: {str(e)}",
            }
