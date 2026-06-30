# OrderAI Phase 1 MVP — PR-1b 基礎建設擴充指令包

> 本文件是交給 **Claude Code Max（CCM / Opus）** 執行的 PR-1b 開發授權書。
> 目的：在 PR-2 業務邏輯實作前，落實「20 萬+ 租戶多市場 SaaS 架構」的三項核心基礎建設。

---

## 專案背景與授權範圍

**目前狀態**：`pingoapple88/orderai-backend` 的 `main` 分支已完成 PR-1（Python FastAPI 基礎架構）。

**本次授權（PR-1b）**：
使用者已正式授權修改 `schema.sql`，以解決 PR-1 遺留的架構瓶頸。請 CCM 執行以下兩項變更，並確保 ORM 與 Alembic 同步更新。

---

## 變更目標 1：金額型別整數化（落實鐵律 7）

為了支援台灣（TWD）、日本（JPY）、泰國（THB）、美國/全球（USD）四個市場的多幣別，並徹底解決浮點數精度問題，所有金額欄位必須改為**整數（Integer）分位**。

**需修改的表與欄位：**
- `plans.monthly_price` (DECIMAL → INTEGER)
- `orders.total_amount` (DECIMAL → INTEGER)
- `order_items.unit_price` (DECIMAL → INTEGER)
- `order_items.subtotal` (DECIMAL → INTEGER)
- `billing_records.amount` (DECIMAL → INTEGER)

*註：`ai_extractions.confidence_score` 屬於機率值（0.00~1.00），維持 `DECIMAL(3,2)` 或改為 `Numeric(3,2)`，不在此限。*

---

## 變更目標 2：引入多租戶隔離鍵（tenant_id）

為了支撟 20 萬+ 店家的規模，以及未來 Pro 版的多成員架構，必須將隔離維度從 `user_id` 提升到 `tenant_id`。

**具體變更：**
1. **建立 `tenants` 表**：
   - `id` (SERIAL PRIMARY KEY)
   - `name` (VARCHAR)
   - `market` (VARCHAR(10) DEFAULT 'tw'，支援 tw/jp/th/us)
   - `created_at`, `updated_at`

2. **修改 `users` 表**：
   - 新增 `tenant_id` (INTEGER REFERENCES tenants(id))
   - 新增 `role` (VARCHAR(50) DEFAULT 'admin'，區分 admin/staff)

3. **修改所有業務表**（加入 `tenant_id` 作為資料隔離鍵）：
   - `user_preferences`
   - `orders`
   - `billing_records`
   - `ai_extractions`
   - `ai_usage_logs`
   - `audit_logs`

*註：`order_items` 因為已有關聯 `orders`，可不加 `tenant_id`，但 `orders` 必須加。*

---

## 執行計畫（PR-1b）

請依序執行以下步驟，完成後提交為 PR-1b。

### 1. 修改 `schema.sql`
- 依照上述目標，直接修改根目錄的 `schema.sql`。
- 這是唯一的 DDL 真實來源。

### 2. 更新 SQLAlchemy ORM 模型
- 修改 `app/models/__init__.py`。
- 新增 `Tenant` 模型。
- 將所有金額欄位的型別從 `Numeric(10, 2)` 改為 `Integer`。
- 在各業務模型新增 `tenant_id` 欄位與 ForeignKey。

### 3. 產生 Alembic Migration
- 由於 PR-1 的 `0001_initial_schema.py` 是直接讀取 `schema.sql` 執行的，修改 `schema.sql` 後，如果資料庫還沒有正式資料，**最乾淨的做法是直接覆蓋 0001 遷移檔**（或者重新產生）。
- 請 CCM 確保 `alembic upgrade head` 可以順利建立更新後的 10 張表。

### 4. 提交 PR-1b
- 建立分支：`feat/pr-1b-multitenant-schema`
- 執行 `pytest` 確認模型修改沒有破壞現有測試。
- 將變更 commit 並推送到遠端。

---

## 執行提示 (給 Claude Code)

1. **完全授權**：本次修改 `schema.sql` 已獲使用者明確授權，請大膽執行。
2. **對齊鐵律**：這兩項變更是為了徹底落實「鐵律 7：金額用整數分位」與「鐵律 3：RBAC 最小權限（透過 tenant_id 隔離）」。
3. **支付架構**：OrderAI 不直接處理任何金流。支付必須透過 `IPaymentProvider` 介面委派給 StallPay。PR-1b 的工作不需實作支付邏輯，但 `IPaymentProvider` 的 ABC 定義必須在 `app/core/interfaces/` 中建立，並在 `app/providers/` 中建立 `stallpay.py` 骨架（內容留空，待 PR-2 補完）。
4. **完成後回報**：請在 PR 描述中說明這 10 張表（原 9 張 + 新增的 tenants）的變更摘要。
