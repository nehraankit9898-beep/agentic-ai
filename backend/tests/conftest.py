"""Shared fixtures for the backend test suite (Phase 8)."""
import os
import sys

import pytest

# Ensure `backend/` is on sys.path so `app.*` imports work from any cwd.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Keep tests hermetic: no .env file interference, web access off by default.
os.environ.setdefault("ALLOW_WEB_ACCESS", "false")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("WORKSPACE_ROOT", os.path.join(os.path.dirname(__file__), "_ws"))


@pytest.fixture
def tool_manager():
    """Fresh ToolManager with all default tools registered."""
    from app.tools.manager import ToolManager

    return ToolManager()


class FakeLLMClient:
    """LLM client stub that returns queued canned responses."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []  # records of message payloads sent to the LLM

    async def chat(self, messages, stream=False):
        self.calls.append(messages)
        if self.responses:
            return self.responses.pop(0)
        return "OK"

    async def check_health(self):
        return True

    def close(self):
        pass


@pytest.fixture
def fake_llm():
    return FakeLLMClient()


@pytest.fixture
def agent_controller(fake_llm, tool_manager):
    """AgentController wired to a fake LLM and real tool manager."""
    from app.agent.controller import AgentController

    return AgentController(fake_llm, tool_manager)
