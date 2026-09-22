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
