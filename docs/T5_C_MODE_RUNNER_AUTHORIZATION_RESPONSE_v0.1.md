# C 模式 Runner 授權回覆單 v0.1｜T5 OrderAI

## 文件核對結果

截至本回覆建立時，僅收到文件名稱「C 模式 Runner 授權回覆單 v0.1」，未收到可讀的回覆單內容、附件、runner 定義、觸發條件或 owner 授權範圍。共享區與目前 T5 repository 中亦未找到同名或含「C 模式」授權文字的文件。因此本回覆**不是 runner 啟用授權**，且不應被解讀為可執行任意背景作業的許可。

| 授權項目 | T5 判定 | 依據／限制 |
|---|---|---|
| 建立或啟用 C 模式 Runner | `BLOCKED` | 未知 runner 定義、owner、部署位置與存活期。 |
| 建立排程或事件觸發 | `BLOCKED` | 未知觸發條件、頻率、延遲要求、停止條件與重試限制。 |
| 讀取正式資料或寫入資料庫 | `BLOCKED` | 未知資料分類、tenant scope、保留期限、加密與稽核責任。 |
| 呼叫 OAuth、LLM、LINE、支付、發票、StallPay／ERP | `BLOCKED` | 既有正式服務 Gate 未解除；本 T5 branch 沒有此授權。 |
| 消費／發布 EventBus 事件 | `BLOCKED` | 未提供核准 whitelist、payload contract 或 transport owner；不得新增第五事件。 |
| 合成 fixture／contract 的一次性驗證 | `NOT_APPLICABLE` | 已有 focused test；不需 background runner。 |

## T5 可安全維持的範圍

T5 目前只持有 `DEMO_MOCK`／synthetic OrderAI contract、fixture與focused harness交接責任。既有 contracts 以 `server_principal_only`、UTC、PII redaction、server-derived idempotency及 audit intent 為邊界，且未知值固定 fail-closed。任何 Runner 不得繞過這些既有約束，亦不得把 fixture 視為正式 provider 或資料庫操作權限。

## 最低必要授權資訊

若中央 owner 期望啟用 C 模式 Runner，請在正式回覆單明確提供以下資料；缺一項即維持 `BLOCKED`：

| 必要欄位 | 需確認內容 |
|---|---|
| owner 與授權期限 | 可核對的責任 owner、批准日期、到期／撤銷方式。 |
| runner 任務定義 | 輸入、輸出、是否需要AI判斷、可接受失敗方式及不可做事項。 |
| trigger 與頻率 | 固定時間／外部事件／人工觸發、預期延遲、最大執行時間與並發限制。 |
| 資料邊界 | 允許的資料分類、company／store scope、PII redaction、保留／刪除與加密規則。 |
| 服務與網路邊界 | 核准 endpoint、provider interface、secret owner、sandbox／正式環境及禁用服務。 |
| 冪等、重試與死信處理 | server-derived key、retry上限、manual review與停止條件。 |
| EventBus 邊界 | 已核准 event whitelist、payload schema、producer／consumer與transport owner。 |
| 稽核與復原 | audit event、UTC evidence path、通知對象、rollback／disable步驟。 |

## T5 回覆與下一步

> **T5 status：`BLOCKED`。** 未提供授權內容前，T5 不建立、部署、啟動或模擬 C 模式 Runner，也不建立排程、webhook、持久服務或資料同步。

本回覆提出 `XREQ-T5-RUNNER-0001` 給中央／runner owner，要求提供上表的最小授權資料。收到正式回覆後，T5 只會重新評估是否存在屬於 OrderAI synthetic contract 的工作；任何實際 runner、external connector、資料讀寫或正式 EventBus 作業仍須另行核准。
