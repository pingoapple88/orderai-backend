"""Provider 工廠：依設定回傳對應 Adapter（集團守則：可替換）。"""
from app.core.config import get_settings
from app.core.interfaces.auth_provider import IAuthProvider
from app.core.interfaces.llm_provider import ILLMProvider
from app.core.interfaces.notification_provider import INotificationProvider
from app.core.interfaces.payment_provider import IPaymentProvider
from app.providers.failover_llm import FailoverLLMProvider
from app.providers.line_auth import LineAuthProvider
from app.providers.http_chat_llm import AnthropicMessagesLLMProvider, OllamaLLMProvider, OpenAICompatibleLLMProvider
from app.providers.stallpay import StallPayProvider

settings = get_settings()


def get_auth_provider() -> IAuthProvider:
    return LineAuthProvider()


def _build_llm_provider(provider: str, *, use_fallback_settings: bool = False) -> ILLMProvider:
    provider = provider.lower()
    connection = {
        "api_key": settings.llm_fallback_api_key if use_fallback_settings else settings.llm_api_key,
        "api_base": settings.llm_fallback_api_base if use_fallback_settings else settings.llm_api_base,
        "model": settings.llm_fallback_model if use_fallback_settings else settings.llm_model,
        "timeout_seconds": (
            settings.llm_fallback_timeout_seconds
            if use_fallback_settings
            else settings.llm_timeout_seconds
        ),
        "allow_empty_api_key": (
            settings.llm_fallback_allow_empty_api_key
            if use_fallback_settings
            else settings.llm_allow_empty_api_key
        ),
    }
    if provider in {"http_chat", "openai_compatible", "openai"}:
        return OpenAICompatibleLLMProvider(**connection)
    if provider == "ollama":
        return OllamaLLMProvider(**connection)
    if provider in {"anthropic", "claude"}:
        return AnthropicMessagesLLMProvider(**connection)
    raise RuntimeError("Unsupported LLM provider: {}".format(provider))


def get_llm_provider() -> ILLMProvider:
    primary = _build_llm_provider(settings.llm_provider)
    fallback_name = settings.llm_fallback_provider.strip()
    if not fallback_name:
        return primary
    return FailoverLLMProvider(
        primary=primary,
        fallback=_build_llm_provider(fallback_name, use_fallback_settings=True),
    )


def get_notification_provider() -> INotificationProvider:
    """回覆/推播訊息提供者（目前 LINE）。"""
    return LineAuthProvider()


def get_payment_provider() -> IPaymentProvider:
    # OrderAI 不自處理金流，一律委派 StallPay
    return StallPayProvider()


# ---- PR-2：佇列工廠（情境一）----
_queue_singleton = None


def get_queue():
    """依 QUEUE_BACKEND 回傳佇列實作（redis|memory）。"""
    global _queue_singleton
    if _queue_singleton is not None:
        return _queue_singleton
    if settings.queue_backend.lower() == "memory":
        from app.providers.queue_memory import InMemoryQueue
        _queue_singleton = InMemoryQueue()
    else:
        from app.providers.queue_redis import RedisQueue
        _queue_singleton = RedisQueue()
    return _queue_singleton


def set_queue(q) -> None:
    """測試注入用。"""
    global _queue_singleton
    _queue_singleton = q
