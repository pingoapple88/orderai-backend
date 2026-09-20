# 青泉谷 P1 Rollback Runbook

本文件只適用於已核准的 OrderAI P1 發布回退。任何回退都必須先停止 P1 入站，保留 append-only audit、Railway 部署版本與資料庫備份證據；不得以刪除事件帳本或案件資料取代問題調查。

## `claimed_at` migration 回退順序

`p1_line_event_claimed_at` 為新版 P1 readiness 的依賴欄位。若先移除欄位、再回退應用程式，仍在執行的新版 API 會因欄位不存在而失敗。因此回退順序必須是先將應用程式回復到 `p1_line_intake_ledger` 相容版本，驗證健康與讀取路由，再執行 Alembic downgrade。

`claimed_at` 是事件處理的操作追蹤時間。執行 downgrade 後，此欄位資料**不可復原**；它不影響 Customer、Order、付款、庫存、出貨、發票或 ERP 送件，但回退前必須保留經核准的資料庫備份與 audit 證據。任何仍為 `processing` 的事件不得自動重試或重新武裝，必須由 owner／manager 依既有人工程序處理。

## 最小驗證

回退後只允許驗證健康、RBAC、append-only audit 與沒有正式交易副作用。任何 LINE webhook、ERP delivery、付款、庫存、出貨或發票動作必須維持停用，直到新的 release candidate 重新通過受控 Gate。
