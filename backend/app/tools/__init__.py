from .base import BaseTool


class CalculatorTool(BaseTool):
    """Tool for performing basic mathematical calculations."""

    name = "calculator"
    description = "Perform basic mathematical calculations (addition, subtraction, multiplication, division)"
    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Mathematical expression to evaluate (e.g., '2 + 2', '10 * 5')",
            }
        },
        "required": ["expression"],
    }

    async def execute(self, expression: str) -> dict:
        """
        Execute a mathematical calculation.

        Args:
            expression: Mathematical expression as string

        Returns:
            Dict with result or error message
        """
        try:
            # Validate input - only allow safe characters
            allowed_chars = set("0123456789+-*/.() ")
            if not all(c in allowed_chars for c in expression):
                return {
                    "success": False,
                    "error": "Invalid characters in expression. Only numbers and basic operators allowed.",
                }

            # Check for dangerous patterns
            if "__" in expression or "import" in expression or "exec" in expression:
                return {
                    "success": False,
                    "error": "Potentially dangerous expression detected.",
                }

            # Safely evaluate the expression
            result = eval(expression, {"__builtins__": {}}, {})

            return {
                "success": True,
                "result": result,
                "expression": expression,
            }
        except ZeroDivisionError:
            return {
                "success": False,
                "error": "Division by zero",
            }
        except SyntaxError:
            return {
                "success": False,
                "error": "Invalid mathematical expression syntax",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Calculation error: {str(e)}",
            }


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
        import os
        from pathlib import Path

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
        import os
        from pathlib import Path

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
        import os
        from pathlib import Path

        try:
            # Security: Prevent path traversal attacks
            base_dir = Path(os.getcwd())
            target_path = Path(path).resolve()

            # Ensure the path is within allowed directory
            try:
                target_path.relative_to(base_dir)
            except ValueError:
                return {
                    "success": False,
                    "error": f"Access denied: Path must be within {base_dir}",
                }

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
