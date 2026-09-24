"""Tests for the AgentController workflow (Phase 8).

The LLM is replaced by a stub (FakeLLMClient in conftest) so these tests
run offline and deterministically.
"""
import json

import pytest


def _understanding_json(**overrides) -> str:
    payload = {
        "needs_tools": False,
        "is_complex": False,
        "tool_calls": [],
        "response": "Hi there!",
    }
    payload.update(overrides)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Simple chat path
# ---------------------------------------------------------------------------

async def test_simple_chat_no_tools(agent_controller, fake_llm):
    fake_llm.responses = [_understanding_json(response="Hello! How can I help?")]
    result = await agent_controller.process_request("hi", session_id="s1")
    assert result.status == "success"
    assert result.requires_confirmation is False
    assert "Hello" in result.message
    # user + assistant messages stored
    history = agent_controller.get_conversation_history("s1")
    roles = [m.role.value for m in history]
    assert roles == ["user", "assistant"]


async def test_session_isolation(agent_controller, fake_llm):
    fake_llm.responses = [_understanding_json(), _understanding_json()]
    await agent_controller.process_request("msg to s1", session_id="s1")
    await agent_controller.process_request("msg to s2", session_id="s2")
    assert len(agent_controller.get_conversation_history("s1")) == 2
    assert len(agent_controller.get_conversation_history("s2")) == 2
    assert agent_controller.clear_session("s1") is True
    assert agent_controller.get_conversation_history("s1") == []


async def test_history_truncated_to_20(agent_controller, fake_llm):
    for i in range(25):
        fake_llm.responses = [_understanding_json(response=f"reply {i}")]
        await agent_controller.process_request(f"message {i}", session_id="long")
    history = agent_controller.get_conversation_history("long")
    assert len(history) <= 20


# ---------------------------------------------------------------------------
# Tool path without confirmation (calculator / date_time)
# ---------------------------------------------------------------------------

async def test_tool_execution_flow(agent_controller, fake_llm):
    understanding = _understanding_json(
        needs_tools=True,
        tool_calls=[{"tool_name": "calculator", "arguments": {"expression": "6*7"}}],
    )
    fake_llm.responses = [understanding, "6 times 7 is 42."]
    result = await agent_controller.process_request("what is 6*7?", session_id="calc")
    assert result.status == "success"
    assert result.requires_confirmation is False
    assert "42" in result.message
    assert result.tool_calls[0].tool_name == "calculator"


async def test_date_time_tool_flow(agent_controller, fake_llm):
    understanding = _understanding_json(
        needs_tools=True,
        tool_calls=[{"tool_name": "date_time", "arguments": {"format": "year"}}],
    )
    fake_llm.responses = [understanding, "It's 2026."]
    result = await agent_controller.process_request("what year is it?", session_id="dt")
    assert result.status == "success"


async def test_unknown_tool_reports_error(agent_controller, fake_llm):
    understanding = _understanding_json(
        needs_tools=True,
        tool_calls=[{"tool_name": "teleporter", "arguments": {}}],
    )
    fake_llm.responses = [understanding, "Sorry, that failed."]
    result = await agent_controller.process_request("beam me up", session_id="u1")
    assert result.status == "error"


# ---------------------------------------------------------------------------
# Confirmation flow (dangerous tools pause execution)
# ---------------------------------------------------------------------------

async def test_dangerous_tool_requires_confirmation(agent_controller, fake_llm):
    understanding = _understanding_json(
        needs_tools=True,
        tool_calls=[
            {"tool_name": "file_writer", "arguments": {"file_path": "x.txt", "content": "hi"}}
        ],
    )
    fake_llm.responses = [understanding]
    result = await agent_controller.process_request("write hi to x.txt", session_id="c1")
    assert result.status == "needs_confirmation"
    assert result.requires_confirmation is True
    state = agent_controller.get_or_create_state("c1")
    assert len(state.pending_tool_calls) == 1


async def test_confirm_resumes_and_executes(agent_controller, fake_llm, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    understanding = _understanding_json(
        needs_tools=True,
        tool_calls=[
            {"tool_name": "file_writer", "arguments": {"file_path": "ok.txt", "content": "done"}}
        ],
    )
    fake_llm.responses = [understanding, "File written successfully."]
    first = await agent_controller.process_request("write ok.txt", session_id="c2")
    assert first.status == "needs_confirmation"

    second = await agent_controller.process_request("write ok.txt", session_id="c2", confirmed=True)
    assert second.status == "success"
    assert (tmp_path / "ok.txt").read_text() == "done"
    state = agent_controller.get_or_create_state("c2")
    assert state.pending_tool_calls == []


# ---------------------------------------------------------------------------
# Fallback heuristics when the LLM returns garbage / fails
# ---------------------------------------------------------------------------

async def test_llm_garbage_falls_back_to_heuristics(agent_controller, fake_llm):
    fake_llm.responses = ["not json at all"]
    result = await agent_controller.process_request("hello", session_id="f1")
    assert result.status == "success"
    assert "Hello" in result.message or "hello" in result.message.lower()


async def test_infer_calculator_from_math_expression(agent_controller, fake_llm):
    # LLM says tools needed but gives no calls -> inference kicks in.
    fake_llm.responses = [
        _understanding_json(needs_tools=True, tool_calls=[]),
        "The answer is 9.",
        "unused",
    ]
    result = await agent_controller.process_request("compute 3 * 3 please", session_id="i1")
    assert result.status == "success"
    assert any(tc.tool_name == "calculator" for tc in result.tool_calls)


async def test_error_recovery_path(agent_controller, fake_llm):
    # division by zero -> tool fails -> error handler explains via LLM
    understanding = _understanding_json(
        needs_tools=True,
        tool_calls=[{"tool_name": "calculator", "arguments": {"expression": "1/0"}}],
    )
    fake_llm.responses = [understanding, "Division by zero is not allowed."]
    result = await agent_controller.process_request("divide 1 by 0", session_id="e1")
    assert result.status == "error"
    assert "zero" in result.message.lower()
