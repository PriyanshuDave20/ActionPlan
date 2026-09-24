import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Backend package root (the directory containing `app/`).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM. "openai-compatible" covers NVIDIA NIM, OpenRouter, vLLM gateways, etc.
    llm_provider: Literal["openai", "openai-compatible", "nvidia", "ollama", "mock"] = "openai-compatible"
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str | None = None

    # LangSmith
    langchain_tracing_v2: bool = False
    langsmith_api_key: str | None = None
    langchain_project: str = "workplace-operations-agent"

    # Vector store / RAG. Zilliz Cloud is the intended V1 backend.
    zilliz_uri: str | None = None
    zilliz_token: str | None = None
    vector_store: Literal["zilliz", "in-memory"] = "zilliz"
    zilliz_collection: str = "workplace_documents"

    embedding_provider: Literal["openai", "openai-compatible", "nvidia", "mock"] = "openai-compatible"
    embedding_model_api: str | None = None
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str | None = None

    # Memory
    memory_backend: Literal["dynamodb", "local"] = "dynamodb"

    # Application data
    data_dir: Path = _BACKEND_ROOT / "data"

    # Web frontend (optional static hosting)
    frontend_dir: Path = _BACKEND_ROOT.parent / "frontend" / "dist"

    # CORS: comma-separated origins allowed to call the API from a browser.
    # FRONTEND_ORIGIN is the single production origin (the Amplify frontend
    # URL) and is merged into the allow-list when set.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    frontend_origin: str | None = None

    # AWS
    aws_region: str = "us-east-2"
    dynamodb_table_name: str = "ActionPlanner"

    @property
    def resolved_llm_api_key(self) -> str | None:
        return self.llm_api_key or self.openai_api_key

    @property
    def resolved_llm_model(self) -> str | None:
        return self.llm_model or self.openai_model

    @property
    def resolved_llm_base_url(self) -> str | None:
        if self.llm_base_url or self.openai_base_url:
            return self.llm_base_url or self.openai_base_url
        if self.llm_provider == "nvidia":
            return "https://integrate.api.nvidia.com/v1"
        return None

    @property
    def resolved_embedding_api_key(self) -> str | None:
        return self.embedding_api_key or self.embedding_model_api or self.openai_api_key or self.llm_api_key

    @property
    def resolved_embedding_base_url(self) -> str | None:
        if self.embedding_base_url:
            return self.embedding_base_url
        if self.embedding_provider == "nvidia":
            return "https://integrate.api.nvidia.com/v1"
        return self.openai_base_url or self.llm_base_url

    @property
    def resolved_cors_origins(self) -> list[str]:
        """Allowed browser origins: CORS_ORIGINS (comma-separated) plus FRONTEND_ORIGIN."""
        origins = [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]
        if self.frontend_origin and self.frontend_origin.strip():
            origins.append(self.frontend_origin.strip())
        return origins


def _apply_runtime_env(settings: Settings) -> None:
    """Export resolved LangSmith tracing variables to the process environment.

    LangChain/LangGraph read tracing configuration from ``os.environ``.
    pydantic-settings loads ``.env`` into the Settings object only, so
    without this export, LANGCHAIN_TRACING_V2 and LANGSMITH_API_KEY in
    ``.env`` never take effect and nothing is traced.
    """
    os.environ.setdefault(
        "LANGCHAIN_TRACING_V2",
        str(settings.langchain_tracing_v2).lower(),
    )
    if settings.langsmith_api_key:
        os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key)
    if settings.langchain_project:
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    _apply_runtime_env(settings)
    return settings