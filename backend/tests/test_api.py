"""API integration tests using FastAPI TestClient (Phase 8).

The real LLM client is swapped for an offline stub, so these tests never
require Ollama to be running.
"""
import json

import pytest
from fastapi.testclient import TestClient


def _understanding_json(**overrides) -> str:
    payload = {
        "needs_tools": False,
        "is_complex": False,
        "tool_calls": [],
        "response": "Stubbed reply",
    }
    payload.update(overrides)
    return json.dumps(payload)


class StubLLM:
    """Minimal async stand-in for app.services.llm_client.LLMClient."""

    def __init__(self, responses=None):
        self.responses = list(responses or [])

    async def chat(self, messages, stream=False):
        if self.responses:
            return self.responses.pop(0)
        return _understanding_json()

    async def check_health(self):
        return True

    def close(self):
        pass


@pytest.fixture
def client(monkeypatch):
    # Patch the LLM before the app lifespan builds the agent.
    monkeypatch.setattr("app.main.LLMClient", lambda: StubLLM())
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# ---------------------------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------------------------

def test_root(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["llm_available"] is True
    assert data["tools_available"] >= 7


def test_list_tools(client):
    resp = client.get("/tools")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["tools"]}
    assert "calculator" in names and "web_search" in names


def test_list_tools_api_alias(client):
    resp = client.get("/api/tools")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Chat + confirmation flow
# ---------------------------------------------------------------------------

def test_chat_simple(client):
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "default"
    assert data["status"] in ("success", "error")


def test_chat_confirmation_roundtrip(client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    # Replace the live agent's LLM with a scripted stub:
    # 1) understanding asks for file_writer (confirmation-gated),
    # 2) final response after confirm.
    from app.main import get_agent

    agent = get_agent()
    agent.conversation_states.clear()
    agent.llm_client = StubLLM(
        [
            _understanding_json(
                needs_tools=True,
                tool_calls=[
                    {
                        "tool_name": "file_writer",
                        "arguments": {"file_path": "api.txt", "content": "via api"},
                    }
                ],
            ),
            "Done — wrote api.txt.",
        ]
    )

    first = client.post(
        "/api/chat", json={"message": "write via api to api.txt", "session_id": "s"}
    )
    assert first.status_code == 200
    assert first.json()["status"] == "needs_confirmation"

    second = client.post("/api/chat/confirm", json={"session_id": "s"})
    assert second.status_code == 200
    assert second.json()["status"] == "success"
    assert (tmp_path / "api.txt").read_text() == "via api"


def test_confirm_without_pending_returns_409(client):
    resp = client.post("/api/chat/confirm", json={"session_id": "nothing-pending"})
    assert resp.status_code == 409


def test_cancel_pending(client):
    from app.main import get_agent

    agent = get_agent()
    agent.conversation_states.clear()
    agent.llm_client = StubLLM(
        [
            _understanding_json(
                needs_tools=True,
                tool_calls=[
                    {
                        "tool_name": "python_executor",
                        "arguments": {"code": "print(1)"},
                    }
                ],
            )
        ]
    )
    first = client.post(
        "/api/chat", json={"message": "run python", "session_id": "cancel-me"}
    )
    assert first.json()["status"] == "needs_confirmation"

    cancelled = client.post("/api/chat/cancel", json={"session_id": "cancel-me"})
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    state = agent.get_or_create_state("cancel-me")
    assert state.pending_tool_calls == []


def test_conversation_history_and_clear(client):
    from app.main import get_agent

    agent = get_agent()
    agent.conversation_states.clear()
    agent.llm_client = StubLLM()
    client.post("/api/chat", json={"message": "remember me", "session_id": "hist"})

    history = client.get("/api/conversation/hist")
    assert history.status_code == 200
    assert len(history.json()["messages"]) >= 1

    cleared = client.delete("/api/conversation/hist")
    assert cleared.json()["success"] is True
    empty = client.get("/api/conversation/hist")
    assert empty.json()["messages"] == []
