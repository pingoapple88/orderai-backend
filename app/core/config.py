"""集中設定（律二：外部化設定）。所有 Key/閾值一律從環境變數讀取。"""
import json
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # App
    app_name: str = "OrderAI Backend"
    environment: str = "development"
    port: int = 8000

    # 資料主權：指向自有 Railway PostgreSQL
    database_url: str = "postgresql+psycopg2://orderai:orderai@localhost:5432/orderai"

    # Auth
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    frontend_url: str = "https://app.orderai.merchcore.ai"
    allowed_origins: str = "https://app.orderai.merchcore.ai"

    # LINE two-channel separation
    line_messaging_channel_id: str = ""
    line_messaging_channel_secret: str = ""
    line_messaging_access_token: str = ""
    line_login_channel_id: str = ""
    line_login_channel_secret: str = ""
    line_login_callback_url: str = "http://localhost:8000/api/v1/auth/line/callback"

    # LLM Provider
    llm_provider: str = "http_chat"
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 0
    llm_allow_empty_api_key: bool = False
    llm_fallback_provider: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_api_base: str = ""
    llm_fallback_model: str = ""
    llm_fallback_temperature: float = 0.0
    llm_fallback_timeout_seconds: int = 60
    llm_fallback_max_retries: int = 0
    llm_fallback_allow_empty_api_key: bool = False

    # AI automation
    ai_confidence_threshold: float = 0.85
    ai_max_items_per_order: int = 30
    ai_max_quantity_per_item: int = 99

    # WO-002 store scope
    default_store_id: int = 0

    # Queue
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: str = "redis"
    queue_name: str = "line_webhook"

    # Qingquangu P1 controlled intake and existing CloudDing adapter
    p1_intake_enabled: bool = False
    p1_pii_encryption_key: str = ""
    p1_identity_hmac_key: str = ""
    p1_attachment_followup_enabled: bool = False
    p1_attachment_max_bytes: int = 10_000_000
    p1_internal_relay_line_user_ids: str = ""
    p1_erp_target_company_id: int = 0
    p1_erp_sales_location_id: int = 0
    p1_erp_product_id_map_json: str = "{}"
    p1_erp_ingest_provider: str = "blocked"
    p1_erp_base_url: str = ""
    p1_erp_service_id: str = "orderai_p1"
    p1_erp_ingress_hmac_secret: str = ""
    p1_erp_timeout_seconds: int = 10

    # Jiezhou P0 is a separate contract. It must not reuse endpoint, identifiers,
    # mapping, credentials, or error codes from any existing ERP. Formal mode stays
    # blocked while endpoint/auth/field contract are [TODO: 待人工確認].
    jiezhou_erp_ingest_provider: str = "blocked"
    jiezhou_tenant_id: int = 0
    jiezhou_company_id: int = 0
    jiezhou_sales_location_id: int = 0
    jiezhou_product_mapping_json: str = "{}"
    jiezhou_contract_reference: str = "[TODO: 待人工確認]"

    # Existing isolated/UAT P1 delivery controls
    p1_isolated_delivery_enabled: bool = False
    p1_erp_isolated_allowed_hosts: str = "localhost,127.0.0.1,::1"
    p1_uat_delivery_enabled: bool = False
    p1_uat_environment_marker: str = ""
    p1_erp_uat_allowed_hosts: str = ""
    p1_uat_seed_enabled: bool = False
    p1_uat_database_host: str = ""
    p1_uat_direct_acceptance_enabled: bool = False

    # StallPay
    stallpay_api_base: str = "https://api.stallpay.merchcore.ai"
    stallpay_api_key: str = ""

    # i18n
    default_lang: str = "zh-TW"

    @property
    def allowed_origins_list(self) -> list:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def p1_internal_relay_user_ids(self) -> set[str]:
        return {value.strip() for value in self.p1_internal_relay_line_user_ids.split(",") if value.strip()}

    @property
    def p1_erp_product_id_map(self) -> dict[int, int]:
        try:
            raw = json.loads(self.p1_erp_product_id_map_json)
        except json.JSONDecodeError as exc:
            raise ValueError("P1_ERP_PRODUCT_ID_MAP_JSON 必須是 JSON object") from exc
        if not isinstance(raw, dict):
            raise ValueError("P1_ERP_PRODUCT_ID_MAP_JSON 必須是 JSON object")
        result: dict[int, int] = {}
        for local_product_id, erp_product_id in raw.items():
            try:
                local_id = int(local_product_id)
                erp_id = int(erp_product_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("P1_ERP_PRODUCT_ID_MAP_JSON 的商品 ID 必須為正整數") from exc
            if local_id <= 0 or erp_id <= 0:
                raise ValueError("P1_ERP_PRODUCT_ID_MAP_JSON 的商品 ID 必須為正整數")
            result[local_id] = erp_id
        return result

    @property
    def jiezhou_product_mapping(self) -> dict[str, str]:
        """讀取捷州獨立商品 mapping；不可引用任何其他 ERP 的商品 ID。"""
        try:
            raw = json.loads(self.jiezhou_product_mapping_json)
        except json.JSONDecodeError as exc:
            raise ValueError("JIEZHOU_PRODUCT_MAPPING_JSON 必須是 JSON object") from exc
        if not isinstance(raw, dict):
            raise ValueError("JIEZHOU_PRODUCT_MAPPING_JSON 必須是 JSON object")
        result: dict[str, str] = {}
        for source_product_key, mapped_product_key in raw.items():
            source = str(source_product_key).strip()
            mapped = str(mapped_product_key).strip()
            if not source or not mapped:
                raise ValueError("JIEZHOU_PRODUCT_MAPPING_JSON 不可包含空白 key 或 value")
            result[source] = mapped
        return result

    @property
    def p1_erp_isolated_allowed_host_set(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.p1_erp_isolated_allowed_hosts.split(",")
            if value.strip()
        }

    @property
    def p1_erp_uat_allowed_host_set(self) -> set[str]:
        return {
            value.strip().lower()
            for value in self.p1_erp_uat_allowed_hosts.split(",")
            if value.strip()
        }


@lru_cache
def get_settings() -> "Settings":
    return Settings()
