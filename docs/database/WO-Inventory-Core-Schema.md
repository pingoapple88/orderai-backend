# WO-Inventory-Core 核心庫存 Schema 定義 v1.0

**發布日期**：2026-09-14
**狀態**：正式凍結 (Adjudicated)
**目標**：建立庫存異動 (Inventory Logs) 與可用量 (Available Stock) 的實體地基。

---

## 1. 庫存異動表：`inventory_logs` (Append-Only)

本表紀錄所有庫存變更，嚴禁 UPDATE 或 DELETE。

| 欄位名 | 型別 | 說明 | 範例 |
|---|---|---|---|
| `id` | BigInteger | PK | |
| `company_id` | BigInteger | FK | 54279733 |
| `store_id` | BigInteger | FK (WO-A7) | 1001 |
| `warehouse_id` | BigInteger | FK | 5001 |
| `sku` | String(50) | 產品編號 | `EGG-PRM-EC10` |
| `qty_delta` | Numeric(18,4) | 變動數量 (含小數) | `-2.0000`, `3.7500` |
| `uom` | String(20) | 單位 | `catty`, `pack` |
| `intent` | Enum | 目的 | `RESERVE`, `COMMIT`, `RELEASE` |
| `idempotency_key` | String(255) | 唯一冪等鍵 | `stallpay:order:9f3a...` |
| `source_ref` | JSONB | 來源單據資訊 | `{"type": "order", "id": "..."}` |
| `created_at` | DateTime | UTC | |

---

## 2. 庫存可用量表：`inventory_summary`

本表反映當前實時庫存狀態。

| 欄位名 | 型別 | 說明 | 範例 |
|---|---|---|---|
| `company_id` | BigInteger | PK/FK | |
| `store_id` | BigInteger | PK/FK | |
| `sku` | String(50) | PK | |
| `on_hand_qty` | Numeric(18,4) | 現有庫存 | 100.0000 |
| `reserved_qty` | Numeric(18,4) | 已預訂(鎖定)庫存 | 10.0000 |
| `available_qty` | Numeric(18,4) | 可用庫存 (on_hand - reserved) | 90.0000 |
| `updated_at` | DateTime | UTC | |

---

## 3. 技術治理要求
1. **律四 (技術棧)**：使用 Python SQLAlchemy 模型實作。
2. **律七 (精確度)**：數量一律使用 `Numeric(18,4)` 或 `Decimal`，嚴禁使用 `Float`。
3. **事件驅動**：庫存變更後需透過 EventBus 發送 `inventory.changed` 事件。

---

## 4. 下一步動作
- **MP (後端)**：實作 `inventory_logs` 的 Append-Only 邏輯與 `inventory_summary` 的原子更新 (Atomic Update)。
