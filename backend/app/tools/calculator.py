from .base import BaseTool
import ast
import asyncio


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

    # Cap expression length: very long inputs are a CPU/memory DoS vector.
    MAX_EXPRESSION_LENGTH = 500

    def validate_input(self, **kwargs) -> tuple[bool, str | None]:
        expression = kwargs.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            return False, "Input 'expression' must be a non-empty string"
        if len(expression) > self.MAX_EXPRESSION_LENGTH:
            return False, f"Expression too long (max {self.MAX_EXPRESSION_LENGTH} characters)"
        return True, None

    @staticmethod
    def _safe_eval(expression: str):
        """Evaluate an arithmetic expression via AST parsing — no eval()."""
        allowed_binops = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
        allowed_unary = (ast.UAdd, ast.USub)

        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                return node.value
            if isinstance(node, ast.BinOp) and isinstance(node.op, allowed_binops):
                left, right = _eval(node.left), _eval(node.right)
                # Bound exponent size to prevent CPU/memory exhaustion
                # (e.g. 9**9**9).
                if isinstance(node.op, ast.Pow) and (
                    abs(right) > 1000 or (left != 0 and abs(left) ** min(abs(right), 1000) > 1e100)
                ):
                    raise ValueError("Exponent too large")
                op = node.op
                if isinstance(op, ast.Add):
                    return left + right
                if isinstance(op, ast.Sub):
                    return left - right
                if isinstance(op, ast.Mult):
                    return left * right
                if isinstance(op, ast.Div):
                    return left / right
                if isinstance(op, ast.FloorDiv):
                    return left // right
                if isinstance(op, ast.Mod):
                    return left % right
                return left ** right
            if isinstance(node, ast.UnaryOp) and isinstance(node.op, allowed_unary):
                val = _eval(node.operand)
                return val if isinstance(node.op, ast.UAdd) else -val
            raise ValueError(f"Disallowed expression element: {type(node).__name__}")

        tree = ast.parse(expression, mode="eval")
        return _eval(tree)

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
            allowed_chars = set("0123456789+-*/.() %")
            if not all(c in allowed_chars for c in expression):
                return {
                    "success": False,
                    "error": "Invalid characters in expression. Only numbers and basic operators allowed.",
                }

            # Safely evaluate the expression with an AST-based evaluator
            # (never uses eval(), so code injection is structurally impossible).
            result = await asyncio.wait_for(
                asyncio.to_thread(self._safe_eval, expression), timeout=5
            )

            return {
                "success": True,
                "output": result,
                "expression": expression,
            }
        except ZeroDivisionError:
            return {
                "success": False,
                "error": "Division by zero",
            }
        except (SyntaxError, ValueError) as e:
            return {
                "success": False,
                "error": f"Invalid mathematical expression: {e}",
            }
        except asyncio.TimeoutError:
            return {
                "success": False,
                "error": "Calculation timed out",
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Calculation error: {str(e)}",
            }
