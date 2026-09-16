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
    # LINE callback 登入成功後導向的 app 前端網域（正式對外子網域）。
    # ⛔ 預設必為 app 網域，嚴禁指向 LP(orderai.merchcore.ai) 或 pages.dev；漏設 FRONTEND_URL 也要導對 app。
    # 與後端 CORS allow_origins 同一網域（app.orderai.merchcore.ai），整條登入鏈一致。
    # 實際值由 Railway 的 FRONTEND_URL 覆蓋。
    frontend_url: str = "https://app.orderai.merchcore.ai"

    # CORS 允許來源：逗號分隔，可多個。從 ENV `ALLOWED_ORIGINS` 讀（律二：外部化設定）。
    # 預設保留現有正式 app 網域 → 沒設 ENV 時行為不變，不破壞現況。
    allowed_origins: str = "https://app.orderai.merchcore.ai"

    # ── LINE 兩支 channel 完全分離（Task 4）──────────────────────────────────
    # Messaging channel：webhook 驗簽（HMAC）+ reply/push
    line_messaging_channel_id: str = ""
    line_messaging_channel_secret: str = ""
    line_messaging_access_token: str = ""
    # Login channel：OAuth authorize + token 交換
    line_login_channel_id: str = ""
    line_login_channel_secret: str = ""
    line_login_callback_url: str = "http://localhost:8000/api/v1/auth/line/callback"

    # LLM Provider（集團守則：AI 服務可替換）
    llm_provider: str = "http_chat"
    llm_api_key: str = ""
    llm_api_base: str = ""
    llm_model: str = ""
    llm_temperature: float = 0.0
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 0
    llm_allow_empty_api_key: bool = False

    # W2：主 Provider 不可用時的備援設定。留空即不啟用備援，維持單一 Provider 行為。
    llm_fallback_provider: str = ""
    llm_fallback_api_key: str = ""
    llm_fallback_api_base: str = ""
    llm_fallback_model: str = ""
    llm_fallback_temperature: float = 0.0
    llm_fallback_timeout_seconds: int = 60
    llm_fallback_max_retries: int = 0
    llm_fallback_allow_empty_api_key: bool = False

    # AI 自動化（律八：信心閾值、fail-closed）
    ai_confidence_threshold: float = 0.85
    ai_max_items_per_order: int = 30
    ai_max_quantity_per_item: int = 99

    # WO-002：v0 一人一店（快照 §九）。LINE 抄單建單的歸屬 store。
    # 0 = 未設定 → worker fail-closed（不建孤兒單）。多店路由見 WO-007。
    default_store_id: int = 0

    # PR-2：非同步佇列（情境一防禦）
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: str = "redis"          # redis | memory（測試/開發）
    queue_name: str = "line_webhook"

    # 青泉谷 P1：預設關閉。啟用時所有個資草稿須以獨立部署注入的 key 加密／雜湊。
    p1_intake_enabled: bool = False
    p1_pii_encryption_key: str = ""
    p1_identity_hmac_key: str = ""
    p1_attachment_followup_enabled: bool = False
    p1_attachment_max_bytes: int = 10_000_000
    p1_internal_relay_line_user_ids: str = ""
    p1_erp_sales_location_id: int = 0
    # JSON object: {"<OrderAI local product id>": <ERP product id>}。
    # 未設定或無效 mapping 時 P1 必須維持人工覆核，絕不可猜測 ERP 商品。
    p1_erp_product_id_map_json: str = "{}"
    # 預設 blocked；僅在具備受控測試或部署設定時可選 http。此設定本身不會啟用 outbox 傳送。
    p1_erp_ingest_provider: str = "blocked"
    p1_erp_base_url: str = ""
    p1_erp_service_id: str = "orderai_p1"
    p1_erp_ingress_hmac_secret: str = ""
    p1_erp_timeout_seconds: int = 10
    # 僅供受控整合測試。預設關閉，且預設僅接受 localhost；不得用於正式 ERP。
    p1_isolated_delivery_enabled: bool = False
    p1_erp_isolated_allowed_hosts: str = "localhost,127.0.0.1,::1"
    # 僅供獨立外部 UAT。與 localhost 隔離模式分開，預設關閉且只接受精準 HTTPS host。
    # 環境必須是 uat 且 marker 必須與此 P1 專用常數完全相同，否則一律拒絕送件。
    p1_uat_delivery_enabled: bool = False
    p1_uat_environment_marker: str = ""
    p1_erp_uat_allowed_hosts: str = ""

    # PR-2：StallPay 金流橋接（情境四）
    stallpay_api_base: str = "https://api.stallpay.merchcore.ai"
    stallpay_api_key: str = ""

    # i18n
    default_lang: str = "zh-TW"

    @property
    def allowed_origins_list(self) -> list:
        """把逗號分隔的 allowed_origins 拆成 list（去空白、濾空項）。"""
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
