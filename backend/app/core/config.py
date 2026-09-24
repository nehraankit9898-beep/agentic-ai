"""Phase 1 – centralized configuration.

All settings are read from environment variables (and an optional .env file).
Field names map directly to the env vars documented in .env.example:

    APP_ENV, DEBUG, OLLAMA_URL, OLLAMA_MODEL, DATABASE_URL, WORKSPACE_ROOT,
    MAX_TOOL_RUNTIME, MAX_AGENT_STEPS, LOG_LEVEL
"""

from functools import lru_cache
from pathlib import Path

from pydantic import ConfigDict, Field
from pydantic_settings import BaseSettings
from typing import ClassVar


DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Environment
    app_env: str = "development"          # development | staging | production
    debug: bool = True
    log_level: str = "INFO"

    # LLM Configuration (Ollama)
    ollama_url: str = ""
    ollama_model: str = ""
    llm_provider: str = "ollama"          # kept for backward compatibility
    llm_base_url: str = ""                # deprecated alias; prefer OLLAMA_URL
    llm_model: str = ""                   # deprecated alias; prefer OLLAMA_MODEL

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000

    # Security
    api_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite+aiosqlite:///./agent.db"

    # Workspace / sandboxing
    workspace_root: str = "./workspace_data"
    max_tool_runtime: int = Field(default=30, ge=1, le=600)   # seconds per tool call
    max_agent_steps: int = Field(default=10, ge=1, le=50)     # runaway-agent guard

    # Cloud LLM fallback (OpenAI-compatible API; keys stay server-side only)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"

    # Conversation memory persistence (SQLite via aiosqlite)
    memory_enabled: bool = True

    # Tool Permissions
    allowed_tools: list[str] = [
        "calculator",
        "file_reader",
        "file_writer",
        "directory_lister",
        "date_time",
        "python_executor",
        "web_search",
        "http_fetcher",
        "text_processor",
        "memory_store",
    ]

    # Sandbox settings
    python_sandbox: bool = True

    # Web search - external access disabled by default for safety
    allow_web_access: bool = False
    web_search_provider: str = "duckduckgo"  # duckduckgo | serper
    serper_api_key: str = ""
    web_timeout_seconds: int = 10

    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- convenience helpers -------------------------------------------------

    @property
    def effective_ollama_url(self) -> str:
        return self.ollama_url or self.llm_base_url or DEFAULT_OLLAMA_URL

    @property
    def effective_ollama_model(self) -> str:
        return self.ollama_model or self.llm_model or DEFAULT_OLLAMA_MODEL

    @property
    def workspace_path(self) -> Path:
        """Absolute, resolved workspace root (all file tools stay inside it)."""
        p = Path(self.workspace_root).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
