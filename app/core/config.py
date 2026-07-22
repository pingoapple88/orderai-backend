"""集中設定（律二：外部化設定）。所有 Key/閾值一律從環境變數讀取。"""
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
    frontend_url: str = "http://localhost:8000"

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
    llm_provider: str = "openai"
    llm_api_key: str = ""
    llm_api_base: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o"

    # AI 自動化（律八：信心閾值、fail-closed）
    ai_confidence_threshold: float = 0.7

    # WO-002：v0 一人一店（快照 §九）。LINE 抄單建單的歸屬 store。
    # 0 = 未設定 → worker fail-closed（不建孤兒單）。多店路由見 WO-007。
    default_store_id: int = 0

    # PR-2：非同步佇列（情境一防禦）
    redis_url: str = "redis://localhost:6379/0"
    queue_backend: str = "redis"          # redis | memory（測試/開發）
    queue_name: str = "line_webhook"

    # PR-2：StallPay 金流橋接（情境四）
    stallpay_api_base: str = "https://api.stallpay.merchcore.ai"
    stallpay_api_key: str = ""

    # i18n
    default_lang: str = "zh-TW"

    @property
    def allowed_origins_list(self) -> list:
        """把逗號分隔的 allowed_origins 拆成 list（去空白、濾空項）。"""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> "Settings":
    return Settings()
