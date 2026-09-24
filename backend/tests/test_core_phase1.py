"""Phase 1 tests – configuration, logging, security helpers."""
import json
import logging

import pytest


# ---- config -----------------------------------------------------------------

def test_settings_defaults():
    from app.core.config import Settings

    s = Settings(_env_file=None)
    assert s.effective_ollama_url == "http://localhost:11434"
    assert s.effective_ollama_model == "llama3.2"
    assert s.max_tool_runtime >= 1
    assert s.max_agent_steps >= 1
    assert "calculator" in s.allowed_tools


def test_settings_env_override(monkeypatch):
    from app.core.config import Settings

    monkeypatch.setenv("OLLAMA_URL", "http://example:9999")
    monkeypatch.setenv("MAX_AGENT_STEPS", "5")
    monkeypatch.setenv("APP_ENV", "production")
    s = Settings(_env_file=None)
    assert s.ollama_url == "http://example:9999"
    assert s.max_agent_steps == 5
    assert s.is_production() is True


def test_settings_deprecated_aliases_fallback():
    from app.core.config import Settings

    s = Settings(_env_file=None, ollama_url="", llm_base_url="http://legacy:11434",
                 llm_model="mistral")
    assert s.effective_ollama_url == "http://legacy:11434"
    assert s.effective_ollama_model == "mistral"


def test_workspace_path_resolves(tmp_path, monkeypatch):
    from app.core.config import Settings

    ws = tmp_path / "wsroot"
    s = Settings(_env_file=None, workspace_root=str(ws))
    p = s.workspace_path
    assert p.is_absolute()
    assert p.exists()


# ---- logging ----------------------------------------------------------------

def test_configure_logging_idempotent():
    from app.core.logging import configure_logging

    configure_logging("INFO")
    n = len(logging.getLogger().handlers)
    configure_logging("DEBUG")
    assert len(logging.getLogger().handlers) == n


def test_json_formatter_includes_context_and_fields():
    from app.core.logging import JsonFormatter, log_event, request_id_var

    token = request_id_var.set("req-123")
    try:
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "hello", (), None
        )
        record.event_data = {"event": "tool_call", "tool_name": "calculator",
                             "duration_ms": 12.5, "status": "ok"}
        payload = json.loads(JsonFormatter().format(record))
        assert payload["request_id"] == "req-123"
        assert payload["tool_name"] == "calculator"
        assert payload["status"] == "ok"
    finally:
        request_id_var.reset(token)


def test_log_event_emits_structured(caplog):
    from app.core.logging import log_event

    with caplog.at_level(logging.INFO):
        log_event(logging.getLogger("x"), "agent_step", step=3, status="success")
    recs = [r for r in caplog.records if getattr(r, "event_data", None)]
    assert recs and recs[-1].event_data["step"] == 3


# ---- security ---------------------------------------------------------------

def test_verify_api_key_ok(monkeypatch):
    from app.core import security

    monkeypatch.setattr(security.settings, "api_key", "secret-abc")
    assert security.verify_api_key("secret-abc") is True
    assert security.verify_api_key("wrong") is False
    assert security.verify_api_key(None) is False


def test_safe_join_blocks_traversal(tmp_path):
    from app.core.security import SecurityError, safe_join

    ok = safe_join(tmp_path, "sub/dir/file.txt")
    assert str(ok).startswith(str(tmp_path.resolve()))

    with pytest.raises(SecurityError):
        safe_join(tmp_path, "../../etc/passwd")

    with pytest.raises(SecurityError):
        safe_join(tmp_path, "/etc/passwd")


# ---- lifecycle --------------------------------------------------------------

@pytest.mark.asyncio
async def test_lifecycle_hooks_order():
    from app.core.lifecycle import Lifecycle

    lc = Lifecycle()
    calls = []
    lc.on_startup(lambda: _fn(calls, "up1"))
    lc.on_startup(lambda: _fn(calls, "up2"))
    lc.on_shutdown(lambda: _fn(calls, "down"))

    async with lc.context():
        pass
    assert calls == ["up1", "up2", "down"]


async def _fn(sink, name):
    sink.append(name)
