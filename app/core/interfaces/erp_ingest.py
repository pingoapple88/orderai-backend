"""IErpIngestProvider — ERP 入站待確認訂單 Adapter 共通介面（律一）。

此模組保留 P1 既有模型，並定義可由不同 ERP Adapter 共用的最小待確認意圖。
在任何 ERP owner 提供 sandbox 與書面契約前，provider 必須 fail-closed：不得
連線、不得猜測 endpoint、不得傳送資料。金額一律整數分位（律七）。

捷州正式契約欄位仍為 ``[TODO: 待人工確認]``；本 PR 僅提供 synthetic contract
與 deterministic fake，沒有任何外部傳輸實作。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Mapping, Optional


class ErpIngestBlockedError(RuntimeError):
    """ERP 連線/契約未就緒時的 fail-closed 錯誤。"""

    def __init__(self, reason_code: str = "ERP_CONNECTION_BLOCKED", message: str = ""):
        super().__init__(message or reason_code)
        self.reason_code = reason_code


@dataclass(frozen=True)
class ErpIngestItem:
    resolved_sku: Optional[str]
    quantity: int
    unit_price_minor: Optional[int]
    price_source: str


@dataclass(frozen=True)
class ErpIngestRequest:
    company_id: int
    order_id: int
    idempotency_key: str
    currency: str
    currency_exponent: int
    items: List[ErpIngestItem]


@dataclass(frozen=True)
class ErpIngestResult:
    provider: str
    reference: str
    status: str                        # accepted / rejected / pending / manual_review
    reason_code: Optional[str] = None  # 只記錄受控錯誤碼，不可放外部 payload


@dataclass(frozen=True)
class PendingCustomerRequest:
    """OrderAI 到既有 ERP Adapter 的待確認客戶標準化請求。"""

    company_id: int
    store_id: int
    sales_location_id: int
    idempotency_key: str
    line_user_id: Optional[str]
    display_name: Optional[str]
    phone: Optional[str]
    contact_authorized: bool
    source_channel: str


@dataclass(frozen=True)
class PendingConfirmationOrderItem:
    product_name: str
    quantity: int
    unit: str
    product_id: Optional[int]


@dataclass(frozen=True)
class PendingConfirmationOrderRequest:
    """OrderAI 到既有 ERP Adapter 的待確認訂單標準化請求。

    此資料模型不含付款、保留、扣庫、出貨或開票欄位。
    """

    company_id: int
    store_id: int
    sales_location_id: int
    idempotency_key: str
    source_event_id: str
    buyer_line_user_id: Optional[str]
    buyer_name: Optional[str]
    requested_for: str
    special_request: Optional[str]
    items: List[PendingConfirmationOrderItem]
    pending_customer_id: Optional[int] = None


@dataclass(frozen=True)
class PendingOrderItem:
    """Provider-neutral 待確認訂單品項；source_product_key 必須外部 mapping。"""

    source_product_key: str
    product_name: str
    quantity: int
    unit: str


@dataclass(frozen=True)
class PendingOrderContent:
    """待確認訂單五欄內容，刻意排除所有正式交易欄位。

    五欄為 ``buyer_name``、``buyer_contact_reference``、``requested_for``、
    ``special_request``、``items``。contact reference 是受控參照，不應放入原始
    電話或外部帳號；實際資料形狀仍為 ``[TODO: 待人工確認]``。
    """

    buyer_name: Optional[str]
    buyer_contact_reference: Optional[str]
    requested_for: Optional[str]
    special_request: Optional[str]
    items: List[PendingOrderItem]


@dataclass(frozen=True)
class PendingOrderIntent:
    """跨 ERP 的最小待確認訂單意圖。

    共通輸入僅含 tenant/company/sales_location 範圍、來源事件、五欄內容、商品
    mapping、冪等鍵與不含 PII 的 audit reference。不得加入 payment、inventory、
    shipment、invoice 或正式 order 欄位。
    """

    tenant_id: int
    company_id: int
    sales_location_id: int
    source_event_id: str
    content: PendingOrderContent
    product_mapping: Mapping[str, str]
    idempotency_key: str
    audit_reference: str


@dataclass(frozen=True)
class PendingOrderMappingConfig:
    """Provider-neutral 的範圍與商品 mapping 設定。

    ``contract_reference`` 只可為契約版本或受控文件參照；捷州正式值目前是
    ``[TODO: 待人工確認]``。空值、不完整範圍或空 mapping 一律不可送件。
    """

    tenant_id: int
    company_id: int
    sales_location_id: int
    product_mapping: Mapping[str, str]
    contract_reference: str

    def readiness_reason(self) -> Optional[str]:
        if self.tenant_id <= 0:
            return "ERP_TENANT_UNMAPPED"
        if self.company_id <= 0:
            return "ERP_COMPANY_UNMAPPED"
        if self.sales_location_id <= 0:
            return "ERP_SALES_LOCATION_UNMAPPED"
        if not self.contract_reference.strip():
            return "ERP_CONTRACT_UNCONFIRMED"
        if not self.product_mapping:
            return "ERP_PRODUCT_MAPPING_MISSING"
        return None

    def validation_reason(self, intent: PendingOrderIntent) -> Optional[str]:
        """檢核範圍、mapping、冪等鍵與審計參照；失敗應轉人工覆核。"""

        not_ready = self.readiness_reason()
        if not_ready:
            return not_ready
        if intent.tenant_id != self.tenant_id:
            return "ERP_TENANT_SCOPE_MISMATCH"
        if intent.company_id != self.company_id:
            return "ERP_COMPANY_SCOPE_MISMATCH"
        if intent.sales_location_id != self.sales_location_id:
            return "ERP_SALES_LOCATION_SCOPE_MISMATCH"
        if not intent.source_event_id.strip():
            return "ERP_SOURCE_EVENT_MISSING"
        if not intent.idempotency_key.strip():
            return "ERP_IDEMPOTENCY_KEY_MISSING"
        if not intent.audit_reference.strip():
            return "ERP_AUDIT_REFERENCE_MISSING"
        if not intent.content.items:
            return "ERP_PENDING_ITEMS_MISSING"
        for item in intent.content.items:
            intent_mapping = intent.product_mapping.get(item.source_product_key)
            configured_mapping = self.product_mapping.get(item.source_product_key)
            if not item.source_product_key.strip() or not intent_mapping or not configured_mapping:
                return "ERP_PRODUCT_MAPPING_MISSING"
            if intent_mapping != configured_mapping:
                return "ERP_PRODUCT_MAPPING_MISMATCH"
            if item.quantity <= 0:
                return "ERP_PENDING_ITEM_QUANTITY_INVALID"
        return None


class IErpIngestProvider(ABC):
    """ERP 待確認訂單入站 Adapter。具體實作見 ``app/providers/``。"""

    @abstractmethod
    async def submit_pending_order(self, request: ErpIngestRequest) -> ErpIngestResult:
        """送出一張待確認訂單；未就緒時 raise ErpIngestBlockedError。"""

    @abstractmethod
    async def create_pending_customer(self, request: PendingCustomerRequest) -> ErpIngestResult:
        """建立待確認客戶；未就緒時 raise ErpIngestBlockedError。"""

    @abstractmethod
    async def submit_pending_confirmation_order(
        self, request: PendingConfirmationOrderRequest
    ) -> ErpIngestResult:
        """建立既有待確認訂單；不得帶付款、保留或扣庫副作用。"""

    async def submit_pending_confirmation_intent(
        self, request: PendingOrderIntent
    ) -> ErpIngestResult:
        """提交 provider-neutral 待確認意圖；預設 fail-closed。

        此延伸方法不可成為既有第三方 provider 的建構期破壞性變更。未選擇
        實作捷州 provider-neutral 契約的 adapter 一律拒絕，不得猜測轉譯或送件。
        """
        raise ErpIngestBlockedError(
            "ERP_CONTRACT_MISMATCH",
            "此 ERP Adapter 未實作 provider-neutral 待確認意圖；不得轉譯或送件。",
        )
