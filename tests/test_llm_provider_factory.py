import pytest

from app.providers import get_llm_provider, settings
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
    with pytest.raises(RuntimeError, match="Unsupported LLM_PROVIDER"):
        get_llm_provider()
