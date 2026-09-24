"""Unit tests for the calculator tool."""
import pytest

from app.tools.calculator import CalculatorTool


@pytest.fixture
def calc():
    return CalculatorTool()


@pytest.mark.parametrize(
    "expression,expected",
    [
        ("2 + 2", 4),
        ("10 - 3", 7),
        ("6 * 7", 42),
        ("100 / 4", 25),
        ("(1 + 2) * 3", 9),
        ("2.5 + 2.5", 5.0),
        ("10 / 4", 2.5),
    ],
)
async def test_basic_arithmetic(calc, expression, expected):
    result = await calc.execute(expression=expression)
    assert result["success"] is True
    assert result["output"] == expected


async def test_division_by_zero(calc):
    result = await calc.execute(expression="5 / 0")
    assert result["success"] is False
    assert "Division by zero" in result["error"]


async def test_invalid_characters_rejected(calc):
    result = await calc.execute(expression="__import__('os')")
    assert result["success"] is False


async def test_dangerous_patterns_rejected(calc):
    for expr in ["1 + __class__", "exec(1)", "import os"]:
        result = await calc.execute(expression=expr)
        assert result["success"] is False


async def test_syntax_error(calc):
    result = await calc.execute(expression="2 ++")
    assert result["success"] is False
    assert "syntax" in result["error"].lower() or "invalid" in result["error"].lower()


async def test_injection_attempt_blocked(calc):
    # Letters are not allowed at all — blocks eval-based escapes.
    result = await calc.execute(expression="open('/etc/passwd').read()")
    assert result["success"] is False
