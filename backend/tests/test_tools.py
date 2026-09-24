"""Unit tests for the remaining tools and the ToolManager (Phase 8)."""
import os
import sys

import pytest

from app.tools.base import BaseTool
from app.tools.date_time import DateTimeTool
from app.tools.directory_lister import DirectoryListerTool
from app.tools.file_reader import FileReaderTool
from app.tools.file_writer import FileWriterTool
from app.tools.manager import ToolManager
from app.tools.python_executor import PythonExecutorTool
from app.tools.web_search import WebSearchTool


# ---------------------------------------------------------------------------
# ToolManager
# ---------------------------------------------------------------------------

def test_manager_registers_default_tools(tool_manager):
    names = {t["name"] for t in tool_manager.list_tools()}
    assert {
        "calculator",
        "date_time",
        "file_reader",
        "file_writer",
        "directory_lister",
        "python_executor",
        "web_search",
    } <= names


async def test_manager_unknown_tool(tool_manager):
    result = await tool_manager.execute_tool("no_such_tool")
    assert result["success"] is False
    assert "not allowed" in result["error"].lower() or "not found" in result["error"].lower()


async def test_manager_validation_failure(tool_manager):
    # calculator requires 'expression'
    result = await tool_manager.execute_tool("calculator")
    assert result["success"] is False


def test_manager_requires_confirmation(tool_manager):
    assert tool_manager.requires_confirmation("file_writer") is True
    assert tool_manager.requires_confirmation("date_time") is False
    assert tool_manager.requires_confirmation("missing_tool") is False


class _BoomTool(BaseTool):
    name = "boom"
    description = "always raises"

    async def execute(self, **kwargs):
        raise RuntimeError("kaboom")


def test_disallowed_tool_not_registered(monkeypatch):
    monkeypatch.setattr("app.tools.manager.settings.allowed_tools", ["calculator"])
    manager = ToolManager()
    names = {t["name"] for t in manager.list_tools()}
    assert names == {"calculator"}


async def test_manager_wraps_tool_exceptions(tool_manager, monkeypatch):
    # Bypass the allowed_tools allowlist so the fake tool can register.
    monkeypatch.setattr("app.tools.manager.settings.allowed_tools", ["*"])
    tool_manager.register_tool(_BoomTool())
    result = await tool_manager.execute_tool("boom")
    assert result["success"] is False
    assert "kaboom" in result["error"]


async def test_execute_tool_bypasses_allowlist_lookup(tool_manager, monkeypatch):
    # Defense-in-depth: even if a tool object were injected into _tools,
    # execution of tools not in allowed_tools must be refused.
    monkeypatch.setattr("app.tools.manager.settings.allowed_tools", ["calculator"])
    tool_manager._tools["file_writer"] = FileWriterTool()
    result = await tool_manager.execute_tool("file_writer", file_path="x.txt", content="y")
    assert result["success"] is False
    assert "not allowed" in result["error"].lower()


# ---------------------------------------------------------------------------
# Date/time tool
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["date", "time", "datetime", "day"])
async def test_date_time_formats(fmt):
    tool = DateTimeTool()
    result = await tool.execute(format=fmt)
    assert result["success"] is True
    assert result["output"]
    assert result["format"] == fmt


async def test_date_time_default():
    tool = DateTimeTool()
    result = await tool.execute()
    assert result["success"] is True
    # default datetime contains a date and a time separator
    assert "-" in result["output"] and ":" in result["output"]


# ---------------------------------------------------------------------------
# File tools (run with cwd pinned to a tmp dir for sandbox checks)
# ---------------------------------------------------------------------------

@pytest.fixture
def in_tmp_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


async def test_file_write_read_roundtrip(in_tmp_cwd):
    writer = FileWriterTool()
    reader = FileReaderTool()

    write_result = await writer.execute(file_path="notes.txt", content="line1\nline2\n")
    assert write_result["success"] is True

    read_result = await reader.execute(file_path="notes.txt")
    assert read_result["success"] is True
    assert "line1" in read_result["content"]


async def test_file_append_mode(in_tmp_cwd):
    writer = FileWriterTool()
    await writer.execute(file_path="log.txt", content="a\n")
    await writer.execute(file_path="log.txt", content="b\n", append=True)
    reader = FileReaderTool()
    result = await reader.execute(file_path="log.txt")
    assert result["content"] == "a\nb"


async def test_path_traversal_blocked_on_read(in_tmp_cwd):
    reader = FileReaderTool()
    result = await reader.execute(file_path="../../etc/passwd")
    assert result["success"] is False
    assert "denied" in result["error"].lower() or "access" in result["error"].lower()


async def test_path_traversal_blocked_on_write(in_tmp_cwd):
    writer = FileWriterTool()
    result = await writer.execute(file_path="../evil.txt", content="x")
    assert result["success"] is False


async def test_read_missing_file(in_tmp_cwd):
    reader = FileReaderTool()
    result = await reader.execute(file_path="does-not-exist.txt")
    assert result["success"] is False
    assert "not found" in result["error"].lower()


async def test_read_max_lines(in_tmp_cwd):
    writer = FileWriterTool()
    body = "\n".join(str(i) for i in range(50))
    await writer.execute(file_path="many.txt", content=body)
    reader = FileReaderTool()
    result = await reader.execute(file_path="many.txt", max_lines=5)
    assert result["lines_read"] <= 6  # 5 lines + truncation marker


async def test_directory_lister(in_tmp_cwd):
    (in_tmp_cwd / "alpha.txt").write_text("a")
    (in_tmp_cwd / "sub").mkdir()
    tool = DirectoryListerTool()
    result = await tool.execute(path=".")
    assert result["success"] is True
    names = {item["name"] for item in result["items"]}
    assert {"alpha.txt", "sub"} <= names


async def test_directory_lister_traversal_blocked(in_tmp_cwd):
    tool = DirectoryListerTool()
    result = await tool.execute(path="/etc")
    assert result["success"] is False


# ---------------------------------------------------------------------------
# Python executor sandbox
# ---------------------------------------------------------------------------

@pytest.fixture
def py_tool():
    return PythonExecutorTool()


async def test_python_basic_output(py_tool):
    result = await py_tool.execute(code="print(2 + 3 * 4)")
    assert result["success"] is True
    assert result["output"].strip() == "14"


async def test_python_allowed_import(py_tool):
    result = await py_tool.execute(code="import math\nprint(math.isqrt(144))")
    assert result["success"] is True
    assert "12" in result["output"]


async def test_python_blocks_os_import(py_tool):
    result = await py_tool.execute(code="import os\nprint(os.getcwd())")
    assert result["success"] is False
    assert "not allowed" in result["error"]


async def test_python_blocks_open(py_tool):
    result = await py_tool.execute(code="open('/etc/passwd').read()")
    assert result["success"] is False


async def test_python_blocks_dunder_escape(py_tool):
    code = "(lambda: ().__class__.__bases__[0])()"
    result = await py_tool.execute(code=code)
    assert result["success"] is False


async def test_python_blocks_infinite_loop(py_tool):
    result = await py_tool.execute(code="while True:\n    pass")
    assert result["success"] is False
    assert "timed out" in result["error"].lower()


async def test_python_syntax_error_reported(py_tool):
    result = await py_tool.execute(code="def f(:\n  pass")
    assert result["success"] is False
    assert "syntax" in result["error"].lower()


async def test_python_runtime_error_captured(py_tool):
    result = await py_tool.execute(code="x = 1 / 0")
    assert result["success"] is False
    assert "ZeroDivisionError" in result["error"]


async def test_python_validate_input_empty(py_tool):
    ok, err = py_tool.validate_input(code="   ")
    assert ok is False


# ---------------------------------------------------------------------------
# Web search tool (network stays disabled — behaviour must be graceful)
# ---------------------------------------------------------------------------

async def test_web_search_disabled_by_default(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "allow_web_access", False)
    tool = WebSearchTool()
    result = await tool.execute(query="python testing")
    assert result["success"] is False
    assert "disabled" in result["error"].lower()


async def test_web_search_validates_query():
    tool = WebSearchTool()
    ok, _ = tool.validate_input(query="")
    assert ok is False
    ok, _ = tool.validate_input(query="ok", max_results=99)
    assert ok is False
