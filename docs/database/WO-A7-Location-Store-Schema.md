# WO-A7 銷售據點與門市 (Store/Location) Schema 定義 v1.0

**發布日期**：2026-09-14
**狀態**：正式凍結 (Adjudicated)
**目標**：解決日日好蛋多據點營運、智販機庫存歸屬問題。

---

## 1. 核心實體：`stores` (銷售據點)

本表為所有銷售行為的物理／邏輯歸屬點。

| 欄位名 | 型別 | 說明 | 範例 |
|---|---|---|---|
| `id` | BigInteger | PK | 1001 |
| `company_id` | BigInteger | FK (UNITYDIGI) | 54279733 |
| `store_code` | String(50) | 唯一編碼 | `EGGS-LOCATION-001` |
| `name` | String(100) | 顯示名稱 | 日日好蛋-內湖瑞光店 |
| `type` | Enum | 類型 | `PHYSICAL`, `VENDING`, `POPUP` |
| `warehouse_id` | BigInteger | 預設對應倉庫 | 5001 |
| `machine_code` | String(50) | 智販機編號 (若有) | `TL-VM-098` |
| `address` | String(255) | 物理地址 | 台北市內湖區... |
| `status` | Enum | 狀態 | `ACTIVE`, `INACTIVE` |
| `created_at` | DateTime | UTC | |

---

## 2. 技術治理要求 (八律遵從)
1. **律三 (RBAC)**：所有查詢必須帶 `company_id`，確保租戶隔離。
2. **律七 (全球合規)**：時間一律為 UTC，地址 PII 需符合加密規範。
3. **資料主權**：本表必須建立於 Jiimoo 指定之 PostgreSQL 資料庫中。

---

## 3. 下一步動作 (Next Steps)
- **MP (後端)**：將此 Schema 轉化為 Alembic Migration 腳本，並在 `merchcore-platform` 執行。
- **MN (AI 解析)**：在訂單解析結果中，`metadata` 需包含對應的 `store_id`。
