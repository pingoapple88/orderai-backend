"""Provider 工廠：依設定回傳對應 Adapter（集團守則：可替換）。"""
from app.core.config import get_settings
from app.core.interfaces.auth_provider import IAuthProvider
from app.core.interfaces.erp_ingest import IErpIngestProvider, PendingOrderMappingConfig
from app.core.interfaces.llm_provider import ILLMProvider
from app.core.interfaces.notification_provider import INotificationProvider
from app.core.interfaces.payment_provider import IPaymentProvider
from app.providers.erp_blocked import BlockedErpIngestProvider
from app.providers.erp_http import CloudDingErpIngestProvider
from app.providers.failover_llm import FailoverLLMProvider
from app.providers.http_chat_llm import AnthropicMessagesLLMProvider, OllamaLLMProvider, OpenAICompatibleLLMProvider
from app.providers.jiezhou_erp import JiezhouBlockedErpIngestProvider
from app.providers.line_auth import LineAuthProvider
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
        "temperature": settings.llm_fallback_temperature if use_fallback_settings else settings.llm_temperature,
        "timeout_seconds": settings.llm_fallback_timeout_seconds if use_fallback_settings else settings.llm_timeout_seconds,
        "allow_empty_api_key": settings.llm_fallback_allow_empty_api_key if use_fallback_settings else settings.llm_allow_empty_api_key,
        "max_retries": settings.llm_fallback_max_retries if use_fallback_settings else settings.llm_max_retries,
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
    return FailoverLLMProvider(primary=primary, fallback=_build_llm_provider(fallback_name, use_fallback_settings=True))


def get_notification_provider() -> INotificationProvider:
    """回覆/推播訊息提供者（目前 LINE）。"""
    return LineAuthProvider()


def get_payment_provider() -> IPaymentProvider:
    # OrderAI 不自處理金流，一律委派 StallPay
    return StallPayProvider()


def get_jiezhou_pending_order_mapping_config() -> PendingOrderMappingConfig:
    """由獨立 ENV 組成捷州 scope/mapping；絕不借用其他 ERP 的設定。"""
    return PendingOrderMappingConfig(
        tenant_id=settings.jiezhou_tenant_id,
        company_id=settings.jiezhou_company_id,
        sales_location_id=settings.jiezhou_sales_location_id,
        product_mapping=settings.jiezhou_product_mapping,
        contract_reference=settings.jiezhou_contract_reference,
    )


def get_jiezhou_erp_ingest_provider() -> IErpIngestProvider:
    """回傳捷州正式 adapter，但本 PR 沒有 endpoint/認證契約，因此始終 blocked.

    ``JIEZHOU_ERP_INGEST_PROVIDER=jiezhou`` 只是未來明確切換意圖；需要的
    tenant/company/location/product/contract 設定不完整時會在 factory 即停止。
    即使完整，仍因正式 endpoint、auth、fields、errors 均 [TODO: 待人工確認]
    而保持 ``ERP_CONNECTION_BLOCKED``，不可能在本 PR 進行網路呼叫。
    """
    if settings.jiezhou_erp_ingest_provider.strip().lower() != "jiezhou":
        return BlockedErpIngestProvider()
    try:
        mapping_config = get_jiezhou_pending_order_mapping_config()
    except ValueError:
        return JiezhouBlockedErpIngestProvider()
    if mapping_config.readiness_reason() is not None:
        return JiezhouBlockedErpIngestProvider()
    return JiezhouBlockedErpIngestProvider()


def get_erp_ingest_provider() -> IErpIngestProvider:
    """既有 P1 ERP ingest factory；捷州只能走其獨立受控 factory。"""
    provider = settings.p1_erp_ingest_provider.strip().lower()
    if provider in {"", "blocked"}:
        return BlockedErpIngestProvider()
    if provider == "jiezhou":
        return get_jiezhou_erp_ingest_provider()
    if provider == "http":
        if (
            not settings.p1_erp_base_url.strip()
            or not settings.p1_erp_service_id.strip()
            or not settings.p1_erp_ingress_hmac_secret.strip()
            or settings.p1_erp_timeout_seconds <= 0
        ):
            return BlockedErpIngestProvider()
        return CloudDingErpIngestProvider(
            base_url=settings.p1_erp_base_url,
            service_id=settings.p1_erp_service_id,
            ingress_hmac_secret=settings.p1_erp_ingress_hmac_secret,
            timeout_seconds=settings.p1_erp_timeout_seconds,
        )
    return BlockedErpIngestProvider()


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
