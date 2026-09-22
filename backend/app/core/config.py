from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LLM Configuration
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.2"

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000

    # Security
    api_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite+aiosqlite:///./agent.db"

    # Tool Permissions
    allowed_tools: list[str] = [
        "calculator",
        "file_reader",
        "file_writer",
        "directory_lister",
        "date_time",
    ]

    # Sandbox settings
    python_sandbox: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
