from .base import BaseTool
import os
from pathlib import Path


class FileWriterTool(BaseTool):
    """Tool for writing content to files."""

    name = "file_writer"
    description = "Write content to a text file (creates or overwrites)"
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Path to the file to write",
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
            },
            "append": {
                "type": "boolean",
                "description": "Whether to append instead of overwrite (default: false)",
                "default": False,
            },
        },
        "required": ["file_path", "content"],
    }
    requires_confirmation = True

    async def execute(
        self, file_path: str, content: str, append: bool = False
    ) -> dict:
        """
        Write content to a file.

        Args:
            file_path: Path to the file
            content: Content to write
            append: Whether to append instead of overwrite

        Returns:
            Dict with success status and info
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

            # Prevent writing to certain dangerous locations
            if target_path.is_dir():
                return {
                    "success": False,
                    "error": "Cannot write to a directory",
                }

            # Create parent directories if they don't exist
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Write content
            mode = "a" if append else "w"
            with open(target_path, mode, encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "message": f"Successfully {'appended to' if append else 'wrote to'} {target_path}",
                "file_path": str(target_path),
                "bytes_written": len(content.encode("utf-8")),
            }

        except PermissionError:
            return {
                "success": False,
                "error": f"Permission denied: {file_path}",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Error writing file: {str(e)}",
            }
