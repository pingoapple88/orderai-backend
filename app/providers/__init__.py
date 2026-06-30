"""Provider 工廠：依設定回傳對應 Adapter（集團守則：可替換）。"""
from app.core.config import get_settings
from app.core.interfaces.auth_provider import IAuthProvider
from app.core.interfaces.llm_provider import ILLMProvider
from app.core.interfaces.payment_provider import IPaymentProvider
from app.providers.line_auth import LineAuthProvider
from app.providers.openai_llm import OpenAILLMProvider
from app.providers.stallpay import StallPayProvider

settings = get_settings()


def get_auth_provider() -> IAuthProvider:
    return LineAuthProvider()


def get_llm_provider() -> ILLMProvider:
    # 依 LLM_PROVIDER 設定回傳對應 Adapter（Python 3.9 相容）
    # Phase 2 可擴充 claude / ollama 分支
    return OpenAILLMProvider()


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
