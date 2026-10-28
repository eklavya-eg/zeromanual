import pytest

from app import llm as llm_module


def test_create_openai_llm_from_environment(monkeypatch) -> None:
    created_with: dict[str, str] = {}
    sentinel = object()

    def create_openai(**kwargs):
        created_with.update(kwargs)
        return sentinel

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1")
    monkeypatch.setattr(llm_module, "ChatOpenAI", create_openai)

    client, provider, model = llm_module.create_llm()

    assert client is sentinel
    assert provider == "openai"
    assert model == "gpt-4.1"
    assert created_with == {"model": "gpt-4.1", "api_key": "test-openai-key"}


def test_create_openrouter_llm_with_request_model(monkeypatch) -> None:
    created_with: dict[str, str] = {}
    sentinel = object()

    def create_openrouter(**kwargs):
        created_with.update(kwargs)
        return sentinel

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setattr(llm_module, "ChatOpenRouter", create_openrouter)

    client, provider, model = llm_module.create_llm(
        provider="openrouter",
        model="google/gemini-2.5-flash",
    )

    assert client is sentinel
    assert provider == "openrouter"
    assert model == "google/gemini-2.5-flash"
    assert created_with == {
        "model": "google/gemini-2.5-flash",
        "api_key": "test-openrouter-key",
    }


def test_create_llm_requires_selected_provider_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(
        llm_module.LlmConfigurationError,
        match="OPENAI_API_KEY is required",
    ):
        llm_module.create_llm(provider="openai")
