# NewModule Legacy Context

> **文件用途**：本文件是針對 **OrderAI（現行程式資產）** 的證據型遷移脈絡包，用於後續評估併入 MerchCore-StallPay 總專案時的獨立 SaaS 化工作。它只彙整已在 GitHub 儲存庫或本工作對話中可驗證的內容；**不新增資料庫設計、API 契約、整合承諾或部署結論**。
>
> **模組識別假設**：本工作所在專案將 Sales Lite 指定為對外品牌、OrderAI Pro 為技術代號；可存取的實體程式資產為 `pingoapple88/orderai-backend` 與 `pingoapple88/orderai-lp`。本文件因而以 **OrderAI** 作為「NewModule」的實體資產範圍。若使用者所指的模組不是 OrderAI，本文件不得作為該模組的技術交接依據。

| 文件欄位 | 內容 |
|---|---|
| 文件名稱 | `NewModule_Legacy_Context.md` |
| 盤點日期 | 2026-08-22（GMT+8） |
| 盤點方式 | 已克隆 GitHub 指定提交版本，僅讀取追蹤檔；未執行服務、遷移或測試 |
| 本次用途 | 遷移脈絡與資產索引；不是已完成的 StallPay 整合紀錄 |
| 不在範圍 | Railway 實際資料庫、已部署環境、正式金鑰、執行期 OpenAPI 快照、真實用戶資料、對話外未提供的需求文件 |

## 1. 已鎖定的權威來源與版本

本文件的程式事實以以下 Git 提交為準。三個本機工作樹在盤點時皆為乾淨狀態；本次未修改、未提交、未推送任何原始碼。

| 資產 | GitHub 位置與分支 | 已鎖定 Commit | 最後提交時間（UTC） | 追蹤檔數 | 本文件中的角色 |
|---|---|---|---|---:|---|
| OrderAI 後端 | [`pingoapple88/orderai-backend`](https://github.com/pingoapple88/orderai-backend/tree/main) `main` | [`c366ef0bbdd161af4e560556501736e3fd968fb0`](https://github.com/pingoapple88/orderai-backend/tree/c366ef0bbdd161af4e560556501736e3fd968fb0) | 2026-08-20T15:13:08Z | 80 | 後端、資料遷移、環境契約、API 與 Adapter 的主要 SSOT [1] |
| OrderAI 招商頁 | [`pingoapple88/orderai-lp`](https://github.com/pingoapple88/orderai-lp/tree/master) `master` | [`d3dd6e37ea90ea1973f6c58f4108f9356cf9afda`](https://github.com/pingoapple88/orderai-lp/tree/d3dd6e37ea90ea1973f6c58f4108f9356cf9afda) | 2026-07-11T17:40:17Z | 2 | 對外定位、直接通路方案與現行招商文案的 SSOT [2] |
| StallPay 目標專案（比對用） | [`pingoapple88/stallpay-v2`](https://github.com/pingoapple88/stallpay-v2/tree/main) `main` | [`f883fa9e617b41e8e0885ad821975f56bb6ae99f`](https://github.com/pingoapple88/stallpay-v2/tree/f883fa9e617b41e8e0885ad821975f56bb6ae99f) | 2026-08-21T09:21:36Z | 425 | 僅用於確認目前程式中被稱為 StallPay 的橋接端是否已有對應文字實作；不是本模組資產 [3] |

> 本文件沒有取代上述 Git 提交。任何遷移、修改或併檔作業均應以指定 commit 的原始碼與其後續受控提交為準。

## 2. 產品定位與獨立販售邏輯

### 2.1 可驗證的現行產品敘事

OrderAI 後端 README 將產品定位為「JiiMoo 集團 AI 訂單辨識平台後端」，並明示其以 Python、FastAPI、SQLAlchemy 與 PostgreSQL 建置。[4] 現行招商頁則以 **LINE 開團／團購主** 為單一受眾，宣稱透過 LINE 訊息解析、自動回覆與庫存扣減，減少人工爬文抄單、漏單、超賣與催款等情境。[5]

招商頁的設計決策紀錄指出，M1–M3 階段決定聚焦「團媽」單一受眾，不加入產業切換器；每個租戶使用自己的 LINE Official Account，推播費用由租戶負擔。[6]

| 項目 | 已存在的程式／文案事實 | 原始來源 |
|---|---|---|
| 核心價值 | 將 LINE 文字訊息判讀為訂單、建立訂單、回覆買家，並以商品型錄帶價 | Worker 與訂單服務 [7] [8] |
| 主要痛點 | 團購群組爬文抄單、漏單、超賣、催款尷尬 | 招商頁痛點區 [5] |
| 主要入口 | LINE Official Account 的 Webhook、LINE Login；不同用途的兩組 LINE channel 已在環境契約中分離 | `.env.example` [9] |
| 租戶邊界 | `stores` 作為租戶隔離邊界，訂單／商品／客戶等資料以 `store_id` 綁定或查詢 | ORM 與訂單服務 [10] [8] |
| 獨立銷售前提 | 個別店家建立自己的 `Store` 與 owner；各租戶使用自身 LINE 官方帳號 | LINE callback、設計決策 [11] [6] |

### 2.2 現行直接通路計費呈現

以下是 `orderai-lp/index.html` 已發佈原始碼中的**直接通路（網站自助註冊）**方案文案。頁面本身明示其價格「截至 2026-05」且「以官網最新方案為準」。此表是**現況轉錄**，不是新定價決策。[5]

| 通路 | 方案 | 月費 | 已列出限制／內容 | 試用或轉換規則 |
|---|---|---:|---|---|
| 直接通路 | Free 免費版 | NT$0 | 100 則 AI 解析、1 位業務；無推播與 CRM | 100 則終身贈送 |
| 直接通路 | Lite 個人版 | NT$390／月 | 1,000 則 AI 解析／月、1 位業務 | 頁面未在該卡片另外列示試用 |
| 直接通路 | Pro 團隊版 | NT$790／月 | 20,000 則 AI 解析／月、3 位業務、推播、取貨提醒、催收、CRM、CSV 匯出 | 14 天 Pro 全功能；或 100 則用完後，依先到者降為 Free，不自動扣款 |
| 企業通路 | Enterprise | 客製報價 | 無限 AI 解析、不限業務人數、API／ERP 對接、白標、SLA、客戶成功經理 | 企業洽詢 |

### 2.3 Sales Lite 專案敘事與現行程式資產的差異

本工作專案的既有領域指示另將產品稱為 **MerchCore Sales Lite／OrderAI Pro**，定位於食品批發、傳統貿易、外勤業務與區域品牌商；其直接通路當前牌價為 NT$790／月、支援 3 位業務、含 14 天試用，並要求未來支援 Direct／Dealer／Enterprise 雙價位 DNA。這些是本工作對話中提供的專案規範，而非本次檢出的 Git 檔案。

因此，下表僅保存兩個來源的**未整合事實**，不將其中任一方推定為最終產品定義。

| 比對面向 | Sales Lite 專案領域指示 | OrderAI 目前 Git 資產 | 遷移時的處理狀態 |
|---|---|---|---|
| 主要受眾 | 食品批發、傳統貿易、外勤業務與區域品牌商 | 團購主／LINE 開團情境 | 兩者尚未有已提交的統一定位決議 |
| 對外名稱 | MerchCore Sales Lite；OrderAI Pro 為技術代號 | OrderAI | 未有已提交的品牌對齊修改 |
| 直接通路主方案 | NT$790／月、3 位業務、14 天試用 | Free／Lite NT$390／Pro NT$790 的三層方案 | NT$790／3 位／14 天在兩者皆可見；其餘分層與受眾不同 |
| 經銷通路 | 未來 Dealer，預計加價約 25–30% | 現行 LP 未列 Dealer 方案 | 無已提交 Dealer 方案文案或程式實作佐證 |
| 企業通路 | 10+ 業務、NT$3,000+、SSO／API／白標／SLA | 客製報價、API／ERP、白標／SLA；未列 NT$3,000+ 或 10+ 門檻 | 無已提交的統一價格與門檻決議 |
| 資料模型中的通路欄位 | 專案規範要求 `plans.channel` | 現行 `plans` 只有 `name`、`monthly_price`、`currency`、額度、成員上限與 `features` | 尚未在目前 `schema.sql` 中出現 `channel` 欄位 [12] |

> **遷移限制**：不得將團購主 LP 的文案、Sales Lite 的 B2B 定位與未來 Dealer 價格合併視為同一份已核准對外主張。遷移前應由產品／商務權責方指定唯一對外版本，並以受控提交保存決議。

## 3. 技術資產 SSOT 索引

本節是**既有資產位置索引**，以協助後續技術團隊接手；不建立或變更 Schema、OpenAPI、事件載荷或部署架構。

### 3.1 技術棧與部署資產

| 層級 | 已存在資產 | 可驗證事實 |
|---|---|---|
| 後端執行環境 | `pyproject.toml`、`Dockerfile` | Python 專案；相依 FastAPI、SQLAlchemy、psycopg2、Alembic、Pydantic Settings、PyJWT、httpx、Redis 與 RQ。Dockerfile 基底為 `python:3.12-slim`，服務入口是 `uvicorn app.main:app`。[13] [14] |
| 資料庫 | `schema.sql`、`alembic/` | PostgreSQL；初始及後續 Alembic 版本檔案存在，包括 0001–0005、WO-006、WO-009 與合併 migration。[12] [15] |
| 本機編排 | `docker-compose.yml` | 具 `db`（PostgreSQL 16）、`redis`、`api`、`worker`、`scheduler` 五個服務；API 容器啟動時執行 `alembic upgrade head`。[16] |
| 外部化設定 | `.env.example` | DB、JWT、LINE Messaging／Login、LLM、信心閾值、Redis／Queue、StallPay bridge 與預設語言皆由環境變數提供。[9] |
| 前端／招商頁 | `orderai-lp/index.html` | 單檔靜態 HTML；此提交內未見可追溯的應用程式前端或後端部署設定。[5] |

### 3.2 資料庫 Schema：現行來源與差異標記

`schema.sql` 自稱為 v3.0、14 張表，並將金額以整數最小貨幣單位儲存、以 `store_id` 作為多租戶隔離鍵。[12] 現行 ORM 模型同時包含 17 個模型類別；除 `schema.sql` 中的 14 個核心表外，還有後續功能加入的 `products`、`order_batches` 與 `order_commits`。[10]

| 資料區域 | 現行可見表／模型 | 原始 SSOT 位置 |
|---|---|---|
| 組織與通路關係 | `companies`、`dealers`、`stores`、`customers` | `schema.sql` 與 `app/models/__init__.py` [12] [10] |
| 方案與使用者 | `plans`、`users`、`user_preferences`、`system_settings` | 同上 [12] [10] |
| 訂單與型錄 | `orders`、`order_items`、`products`、`order_batches`、`order_commits` | ORM、WO-006／WO-009 migrations [10] [15] |
| 帳務與 AI | `billing_records`、`ai_extractions`、`ai_usage_logs` | `schema.sql` 與 ORM [12] [10] |
| 稽核 | `audit_logs` | `schema.sql` 與訂單服務 [12] [8] |

> **SSOT 注意事項**：`schema.sql` 的 14 張表敘述與 ORM 的 17 個模型類別不完全一致；後續遷移應以「指定 commit 下的 Alembic 線性版本＋實際部署資料庫的 migration revision」交叉確認，不能僅依本文件或僅依 `schema.sql` 重建資料庫。

### 3.3 API 介面索引與 OpenAPI 狀態

FastAPI 入口在 `app/main.py`，已掛載 `/health` 與 `/api/v1` 下的 auth、webhook、orders、products、batches 路由。[17] 因該提交未追蹤獨立的 `openapi.yaml`、`openapi.json` 或匯出腳本，本文件僅提供**已實作路由索引**；不得把此表當作正式 OpenAPI 定義。正式 OpenAPI 應由指定 commit 的可驗證啟動環境輸出後，連同生成時間與 commit hash 一併歸檔。

| 路由群組 | 已實作方法與路徑 | 存取／功能摘要 | 原始來源 |
|---|---|---|---|
| 健康檢查 | `GET /health` | 回傳服務狀態與 UTC 時間戳 | `app/main.py` [17] |
| 身分認證 | `GET /api/v1/auth/line/login`、`GET /api/v1/auth/line/callback`、`GET /api/v1/auth/me` | LINE Login、state cookie 比對、首次登入建立 Store／owner、JWT 轉導、目前使用者資訊 | `app/api/v1/auth.py` [11] |
| LINE Webhook | `POST /api/v1/webhooks/line` | LINE 簽章驗證後交由 Queue 處理 | `app/api/v1/webhook.py` [18] |
| 訂單 | `GET /api/v1/stores/{store_id}/orders`、`GET /{order_id}`、`POST /{order_id}/confirm`、`PUT /{order_id}` | 列表、讀取、確認與修正；均由 store access 驗證 | `app/api/v1/orders.py`、`order_service.py` [8] |
| 商品型錄 | `GET/POST /api/v1/stores/{store_id}/products`、`PATCH/DELETE /{product_id}` | 讀取、建立、更新、軟刪除店家商品 | `app/api/v1/products.py` [19] |
| 開團批次 | `POST/GET /api/v1/stores/{store_id}/batches`、`POST /{batch_id}/close`、`POST /{batch_id}/parse`、`POST /{batch_id}/commit`、`GET /{batch_id}/summary` | 建立、列出、封團、解析、提交與彙總 | `app/api/v1/batches.py` [20] |

檔案 `app/api/v1/superadmin.py` 存在，但目前入口檔已明確註記「本期不掛載」，故未列為公開 API。[17]

## 4. 目前實作進度：已存在功能清單

以下功能清單以已提交的 Python、SQL、設定與測試檔案存在為依據。**未在本盤點中啟動服務、連線 Railway 或執行 pytest**，因此「已存在」不等於已在正式環境驗收、已上線或已完成商務流程。

| 範圍 | 已存在且可由來源確認的內容 | 佐證 |
|---|---|---|
| 基礎服務骨架 | FastAPI 入口、健康檢查、標準錯誤回應、CORS 設定、SQLAlchemy、Alembic、Docker 與 compose 編排 | [17] [4] [14] [16] |
| 使用者與租戶建立 | LINE Login callback 驗證 state；首次登入建立 Store 與 owner User；簽發 JWT | [11] |
| 訂單管理 | Store-scoped 訂單列表／讀取；建立、更新、確認；訂單明細與整數分金額計算 | [8] |
| 稽核與內部事件 | 訂單建立、更新、確認寫入 `audit_logs`，並發布 `order.created`、`order.updated`、`order.confirmed` | [8] |
| LINE 接單 | LINE Webhook 簽章驗證、非同步 Queue 入口；worker 取文字訊息、解析訂單、建單、回覆買家 | [18] [7] |
| AI 控制 | 可透過 `LLM_PROVIDER` 選擇 `openai`／`claude`／`ollama`；低於信心閾值不建單並通知 | [9] [7] |
| 商品型錄 | Store 自有商品、別名、單價、軟刪除；解析後可嘗試由型錄帶入價格 | [10] [7] |
| 批次抄單 | 建立／關閉批次、文字解析、低信心或未匹配行待人工處理、SHA-256 去重提交、彙總 | `app/services/batch_service.py`、WO-009 routes [20] |
| 付款橋接 Adapter | `IPaymentProvider` 的 `StallPayProvider` 類別，能建立付款與查詢付款狀態 | [21] |
| 排程／輪詢資產 | compose 內有 scheduler；程式存在 `app/scheduler.py`，並可呼叫 payment provider 查詢狀態 | [16] |

### 4.1 尚無法以本次盤點證實的項目

| 項目 | 狀態 |
|---|---|
| 正式 Railway 部署網址、服務健康狀態與目前資料庫 revision | 無可存取的部署證據；未驗證 |
| 正式 OpenAPI 匯出檔 | 目前 Git 提交未追蹤獨立檔案；未產生 |
| 金鑰實值與 secrets 管理位置 | `.env.example` 僅提供名稱與範例值；實值未讀取、未記錄 |
| 真實客戶資料、現有店家數、付費／試用轉換、AI 實際使用量 | 無資料庫／分析報表來源；未驗證 |
| OrderAI 對 StallPay 的端對端支付流程 | Adapter 有程式碼，但本次比對 StallPay 指定提交時，未找到與 `v1/payments` 或 OrderAI 字樣相符的文字實作；不可標示為已完成對接 [21] [3] |
| Sales Lite 原先要求的招商頁 v1→v2 修改 | 本次可取得的 LP 為兩檔案儲存庫版本；沒有接收到先前所稱的 Sales Lite v1 原始 HTML 交付檔，故未完成該改版 |

## 5. 跨模組依賴、資料邊界與事件

### 5.1 OrderAI 讀取／寫入的外部或跨服務資料

| 對象 | 方向 | 程式可見資料或行為 | 設定來源／程式位置 |
|---|---|---|---|
| PostgreSQL | 讀寫 | Store、使用者、客戶、商品、訂單、批次、AI 記錄、帳務與稽核資料 | `DATABASE_URL`；SQLAlchemy／Alembic [9] [12] |
| LINE Login | 對外讀取 | OAuth 授權與 code 交換，用於取得登入者 profile | `LINE_LOGIN_*`；`auth.py` [9] [11] |
| LINE Messaging API | 進站與出站 | 接收 Webhook event；驗簽；向 LINE 買家回覆訊息 | `LINE_MESSAGING_*`；Webhook／worker [9] [18] [7] |
| LLM Provider | 對外讀取 | 依文字與產業類型擷取訂單內容、信心分數與品項 | `LLM_PROVIDER`、`LLM_API_*`、`AI_CONFIDENCE_THRESHOLD` [9] [7] |
| Redis／RQ | 內部服務 | 將 LINE Webhook 工作排入 `line_webhook` queue，供 worker 消化 | `REDIS_URL`、`QUEUE_*` [9] [18] |
| StallPay | 對外呼叫 | 建立付款：`POST {STALLPAY_API_BASE}/v1/payments`；查詢付款：`GET {STALLPAY_API_BASE}/v1/payments/{reference}`；Bearer token 由 ENV 提供 | `STALLPAY_API_*`；`StallPayProvider` [9] [21] |

### 5.2 事件與 Webhook 邊界

OrderAI 現行可確認的外部 Webhook 是**接收** LINE 的 `POST /api/v1/webhooks/line`；請求在驗簽後被放入 Queue。[18] 處理 worker 使用可替換 LLM 與通知 provider，低信心結果採 fail-closed，不建立訂單。[7]

訂單服務在完成資料庫提交後，會於同程序的 EventBus 發布以下事件。EventBus 的實作為同步、in-process 的抽象，程式註解表示後續可替換為 Redis／Kafka；因此這些不是已對外投遞的 HTTP Webhook。[8] [22]

| 事件名稱 | 觸發時機 | 現有 payload 欄位 | 對外 Webhook 狀態 |
|---|---|---|---|
| `order.created` | 建立訂單後 | `order_id`、`store_id` | 未見 HTTP callback 實作；目前為內部 EventBus |
| `order.updated` | 更新訂單後 | `order_id`、`store_id` | 同上 |
| `order.confirmed` | 確認訂單後 | `order_id`、`store_id` | 同上 |

> **整合事實界線**：StallPayProvider 對外依賴的 payment endpoint 與 Authorization 方式已存在於 OrderAI；但接受方 API 的正式契約、事件回傳方式、冪等規則、重試規則與認證交接，均未有可在這三個指定提交間互相佐證的完成紀錄。這些應保留為後續技術專案的受控整合工作，不得寫成既有成果。

## 6. 遷移時必須保留的決策與不可假設事項

### 6.1 已有來源可確認的決策

| 決策／約束 | 已有來源事實 |
|---|---|
| 後端主技術 | README 與 `pyproject.toml` 指向 Python、FastAPI、SQLAlchemy、PostgreSQL；README 記載曾由 Node.js／Express 重構 | [4] [13] |
| 金額表示 | `schema.sql`、ORM 與訂單服務均以整數最小貨幣單位處理金額 | [12] [10] [8] |
| 租戶邊界 | Store 是租戶隔離單位；訂單、商品與多數資料模型使用 `store_id` | [10] [8] |
| AI 安全處理 | LLM 可依設定切換；信心低於閾值時不建單 | [9] [7] |
| LINE Channel 分離 | Messaging 與 Login 使用不同環境變數、不同用途 | [9] |
| LINE 接單的 v0 限制 | Worker 註明一人一店、以 default store 路由；找不到 Store／owner 即 fail-closed | [7] |
| 招商頁受眾決定 | M1–M3 聚焦團購主單一受眾，不設產業切換器 | [6] |

### 6.2 需要指定權責方確認、不得自行補齊的事項

| 主題 | 已知事實 | 需要的下一份權威產出 |
|---|---|---|
| 產品名稱與目標市場 | Sales Lite 的 B2B 敘事與 OrderAI LP 的團購主敘事並存 | 由產品／商務權責方核准的定位與對外文案版本 |
| 通路與定價 | Sales Lite 要求 Direct／Dealer／Enterprise；現行 DB／LP 未完整呈現 Dealer 與 `plans.channel` | 由產品與技術權責方共同核准的定價與資料遷移決策 |
| API SSOT | FastAPI 路由存在，但沒有追蹤的 OpenAPI 匯出檔 | 由後端維護者自指定 commit／環境輸出的版本化 OpenAPI 工件 |
| 資料庫 SSOT | `schema.sql` 14 表與 ORM 17 模型並存，且已有多個 Alembic 版本 | 以 deployed revision 為基準的 migration manifest 與回復策略 |
| StallPay 金流橋接 | OrderAI 端有 Provider，但比對之 StallPay commit 未見相符接收端文字實作 | 兩端維護者共同簽認的 API 合約、認證、冪等與回調／輪詢責任界線 |
| 資料搬遷 | 本次未接觸任何正式 DB 或 PII | Railway 備份、資料分類、加密與搬遷計畫；不得以本文件取代 |
| 上線狀態 | 僅證實 Git 內有源碼與測試檔 | CI／測試紀錄、部署紀錄、環境健康檢查與營運驗收證據 |

## 7. 實體資產清單與保存建議

下表列出的內容均可從鎖定提交重新取得。除本文件外，本次沒有產生或保存任何可獨立執行的程式碼副本。

| 分類 | 實體位置 | 類型 | 用途 | 最後可驗證版本 |
|---|---|---|---|---|
| 後端應用程式 | `pingoapple88/orderai-backend/app/` | Python 原始碼 | API、服務、模型、Provider、Worker | `c366ef0…68fb0` [1] |
| 資料庫遷移 | `pingoapple88/orderai-backend/alembic/` | Alembic Python migration | Schema 演進 | `c366ef0…68fb0` [1] |
| Schema 快照 | `pingoapple88/orderai-backend/schema.sql` | SQL | 14 表 v3.0 表述與初始方案資料 | `c366ef0…68fb0` [12] |
| 環境契約 | `pingoapple88/orderai-backend/.env.example` | 範例設定 | 外部服務與環境變數名稱 | `c366ef0…68fb0` [9] |
| 容器部署 | `Dockerfile`、`docker-compose.yml` | 容器設定 | 本機／可攜部署基礎 | `c366ef0…68fb0` [14] [16] |
| 後端測試 | `pingoapple88/orderai-backend/tests/` | pytest 原始碼 | 健康檢查、Webhooks、認證、批次、產品等測試資產 | `c366ef0…68fb0` [1] |
| 招商頁 | `pingoapple88/orderai-lp/index.html` | 靜態 HTML | 現行對外 LP 文案與視覺實作 | `d3dd6e…9afda` [2] |
| 招商頁決策紀錄 | `pingoapple88/orderai-lp/DESIGN_DECISIONS.md` | Markdown | 受眾、圖示、LINE@ 與後端技術棧的設計決策 | `d3dd6e…9afda` [6] |
| 遷移目標比對來源 | `pingoapple88/stallpay-v2/` | Git 儲存庫 | 僅供確認目前橋接落點，不屬 OrderAI 本體 | `f883fa…ae99f` [3] |

## 8. 本文件的交接邊界

本文件已將可驗證的核心資產位置、版本、現有功能、資料模型來源、已掛載 API、外部依賴與內部事件列出；它沒有建立新程式碼、改動 Schema、建立 OpenAPI 檔、改寫 LP、連線外部服務或操作客戶資料。

若要將此模組遷入 MerchCore-StallPay 總專案進行獨立 SaaS 化，後續工作必須在 Jiimoo 自有 Git 與 Railway 基礎設施中進行，並將每個新的技術決策、Schema migration、OpenAPI 工件、環境變數與端對端驗證證據以新的受控提交保存。本文件僅作為遷移前的脈絡與來源索引。

## 參考來源

[1]: https://github.com/pingoapple88/orderai-backend/tree/c366ef0bbdd161af4e560556501736e3fd968fb0 "OrderAI Backend — locked commit c366ef0"
[2]: https://github.com/pingoapple88/orderai-lp/tree/d3dd6e37ea90ea1973f6c58f4108f9356cf9afda "OrderAI Landing Page — locked commit d3dd6e3"
[3]: https://github.com/pingoapple88/stallpay-v2/tree/f883fa9e617b41e8e0885ad821975f56bb6ae99f "StallPay v2 — comparison commit f883fa9"
[4]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/README.md "OrderAI Backend README"
[5]: https://github.com/pingoapple88/orderai-lp/blob/d3dd6e37ea90ea1973f6c58f4108f9356cf9afda/index.html "OrderAI LP"
[6]: https://github.com/pingoapple88/orderai-lp/blob/d3dd6e37ea90ea1973f6c58f4108f9356cf9afda/DESIGN_DECISIONS.md "OrderAI LP Design Decisions"
[7]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/workers/line_worker.py "LINE webhook worker"
[8]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/services/order_service.py "Order service"
[9]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/.env.example "OrderAI environment-variable contract"
[10]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/models/__init__.py "OrderAI SQLAlchemy models"
[11]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/api/v1/auth.py "OrderAI LINE authentication routes"
[12]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/schema.sql "OrderAI schema.sql"
[13]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/pyproject.toml "OrderAI Python dependencies"
[14]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/Dockerfile "OrderAI Dockerfile"
[15]: https://github.com/pingoapple88/orderai-backend/tree/c366ef0bbdd161af4e560556501736e3fd968fb0/alembic "OrderAI Alembic migrations"
[16]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/docker-compose.yml "OrderAI docker-compose"
[17]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/main.py "OrderAI FastAPI entrypoint"
[18]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/api/v1/webhook.py "OrderAI LINE webhook ingress"
[19]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/api/v1/products.py "OrderAI product routes"
[20]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/api/v1/batches.py "OrderAI batch routes"
[21]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/providers/stallpay.py "OrderAI StallPay payment adapter"
[22]: https://github.com/pingoapple88/orderai-backend/blob/c366ef0bbdd161af4e560556501736e3fd968fb0/app/core/events.py "OrderAI event bus"
