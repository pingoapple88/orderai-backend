import pytest

from app.providers import get_llm_provider, settings
from app.providers.failover_llm import FailoverLLMProvider
from app.providers.http_chat_llm import AnthropicMessagesLLMProvider, OllamaLLMProvider, OpenAICompatibleLLMProvider


def test_http_chat_uses_http_adapter(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "http_chat")
    assert isinstance(get_llm_provider(), OpenAICompatibleLLMProvider)


def test_ollama_uses_its_http_adapter(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    assert isinstance(get_llm_provider(), OllamaLLMProvider)


def test_anthropic_uses_its_adapter(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    assert isinstance(get_llm_provider(), AnthropicMessagesLLMProvider)


def test_unknown_provider_fails_closed(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "unsupported")
    with pytest.raises(RuntimeError, match="Unsupported LLM provider"):
        get_llm_provider()


def test_configured_fallback_uses_independent_connection_settings(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "llm_api_key", "primary-key")
    monkeypatch.setattr(settings, "llm_api_base", "https://primary.example/v1")
    monkeypatch.setattr(settings, "llm_model", "primary-model")
    monkeypatch.setattr(settings, "llm_fallback_provider", "claude")
    monkeypatch.setattr(settings, "llm_fallback_api_key", "fallback-key")
    monkeypatch.setattr(settings, "llm_fallback_api_base", "https://fallback.example/v1")
    monkeypatch.setattr(settings, "llm_fallback_model", "fallback-model")

    provider = get_llm_provider()

    assert isinstance(provider, FailoverLLMProvider)
    assert provider.primary.api_key == "primary-key"
    assert provider.fallback.api_key == "fallback-key"
    assert provider.primary.api_base == "https://primary.example/v1"
    assert provider.fallback.api_base == "https://fallback.example/v1"
