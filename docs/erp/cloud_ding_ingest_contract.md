# 雲鼎 ERP 入站扣庫契約 (CloudDing Ingest Contract) v1.0.0 凍結版

**路徑** `docs/erp/cloud_ding_ingest_contract.md`
**repo** `pingoapple88/orderai-backend` (Python FastAPI + SQLAlchemy)
**狀態** **已凍結 (Frozen)** - 由 Dennis 於 2026-09-14 裁決並簽署
**寫入閘** Dennis (Manus AI Managing Director)

---

## 0. 邊界與主權
1. 本契約定義 **StallPay/各通路 → 雲鼎 ERP** 的**單向**入站事件；ERP **只寫自己的 DB**（律三、資料主權）。
2. ERP 是**庫存事實的唯一真相**。扣庫成敗由 ERP 裁定，上游不得自行認定「已扣」。
3. 事件外殼採 **Contract v1.8 envelope**。

---

## 1. 端點與認證
- **路徑**: `POST /api/erp/ingest`
- **Owner**: ERP Core (MP)
- **認證**: **HMAC-SHA256**，secret 來自 ENV `INGEST_HMAC_SECRET`。

---

## 2. 核心裁決與規範 (Dennis Adjudication)

| 項目 | 裁決結果 | 執行細節 |
|---|---|---|
| **金額單位** | **強制分位整數 (Minor Units)** | 遵循律七。所有 Payload 金額必須為整數，TWD 以 1 元為單位 (exponent=0)。 |
| **負庫存政策** | **物理優先 (Physical-First)** | 針對智販機 (Vending)，若貨已出但帳面不足，**允許暫時記為負值**，但必須寫入 `audit_logs` 並告警。 |
| **倉庫規則** | **預設對應 (Default Mapping)** | `warehouse_id` 可為空，系統將根據 `store_id` 自動對應至預設倉庫。 |
| **技術棧** | **Python FastAPI** | 遵循主權守則律四，所有後端實作必須使用 Python。 |

---

## 3. 數據模型 (Payload)

```json
{
  "event_id": "uuid-v4",
  "company_id": 54279733,
  "idempotency_key": "unique-request-id",
  "payload": {
    "source_ref": "LINE-EVT-123",
    "channel": "vending",
    "store_id": 101,
    "items": [
      { "sku": "EGG-30", "qty": 2, "unit_price_minor": 12000 }
    ]
  }
}
```

---

## 4. 稽核與冪等 (律三、律八)
- **去重鍵**: `(company_id, idempotency_key)` 唯一約束。
- **審計日誌**: 所有扣庫動作必須寫入 `audit_logs` (Append-only)，包含 `event_id` 與 `source_ref`。

---

## 版本紀錄
- v1.0.0 (2026-09-14): 由 Dennis 完成 §8 裁決，正式凍結規格。
