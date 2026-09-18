import os

import pytest

from app.config import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_CLOUD_TESTS", "").lower() != "1",
    reason="Set RUN_CLOUD_TESTS=1 to run live cloud integration tests.",
)


def test_cloud_config_is_present():
    settings = Settings()
    assert settings.llm_provider
    assert settings.embedding_provider
    assert settings.memory_backend
    assert settings.aws_region
    assert settings.dynamodb_table_name


def test_nvidia_provider_resolves_base_url():
    settings = Settings(_env_file=None)
    settings.llm_provider = "nvidia"
    assert settings.resolved_llm_base_url == "https://integrate.api.nvidia.com/v1"


def test_mock_stack_needs_no_credentials():
    settings = Settings(
        llm_provider="mock",
        embedding_provider="mock",
        vector_store="in-memory",
        memory_backend="local",
    )
    assert settings.resolved_llm_api_key is None
    assert settings.resolved_embedding_api_key is None