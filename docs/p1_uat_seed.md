# 青泉谷 P1 OrderAI 隔離 UAT 合成基準

此入口的目的僅為建立、驗證及移除**隔離 UAT** 的最小合成租戶資料；它不是服務啟動程序、不是 LINE webhook、不是正式客戶匯入，也不會建立正式訂單。

## 強制守門

執行前必須同時滿足下列條件；任一不符即回傳 blocked 並不寫入資料。

| 條件 | 必須值 |
|---|---|
| `ENVIRONMENT` | `uat` |
| `P1_UAT_ENVIRONMENT_MARKER` | `qingquan-p1-uat` |
| `P1_UAT_SEED_ENABLED` | `true` |
| `P1_UAT_DATABASE_HOST` | 與 `DATABASE_URL` 完全一致的 `.railway.internal` host |

因此不得在 localhost、正式環境、外部資料庫或未標記環境執行。此入口不會輸出資料庫 URL、密鑰、草稿內容或任何個資。

## 手動操作

僅在隔離 OrderAI UAT service 的受控 shell 內，人工執行一種動作：

```text
python scripts/p1_uat_seed.py --seed
python scripts/p1_uat_seed.py --verify
python scripts/p1_uat_seed.py --clear
```

`--seed` 可重跑，僅建立合成 company、直接通路 `plans`、store、owner 和一項合成商品。`--verify` 唯讀檢查正式 Customer、Order、BillingRecord、LINE webhook event 為零。`--clear` 僅會刪除精準識別的合成資料；若偵測到上述任一正式副作用，會 fail-closed 拒絕清理，以保留人工調查證據。

容器啟動命令會先執行標準 `alembic upgrade head`，再啟動 API，確保空白資料庫具備既有 schema。這只套用 migration，**不會呼叫**種子程式；種子仍必須由隔離 service 的人工受控 shell 明確執行。`railway.json` 亦保留同一 pre-deploy 宣告，供支援該欄位的部署平台採用。

## P1 邊界

初始種子不會建立待確認客戶、待確認訂單、outbox、付款、庫存預留、扣庫、出貨或開票。外部 ERP 送件需另依人工覆核、精確 UAT host allowlist、HMAC 與後續直接受控驗收完成；LINE 測試 channel / webhook 更必須在直接驗收通過後另行處理。
