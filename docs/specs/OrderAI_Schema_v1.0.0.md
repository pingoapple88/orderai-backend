# OrderAI 解析輸出 Schema 凍結 v1.0.0 (Adjudicated)

**repo** `pingoapple88/orderai-backend`
**依據** WO-T5-1～T5-6、八律律三／律七／律八、Contract v1.8
**狀態** 凍結 (2026-09-14)
**裁決人** Dennis (Manus AI)

---

## 0. 本 Schema 的邊界
本 Schema 是**解析器的唯一輸出格式**，代表「一次 AI 解析的結果草稿」。它**不是**訂單，不含金額合計，且不直接寫入 `orders` 表。

---

## 1. 頂層物件 `OrderParseResult`

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `schema_version` | String | ✅ | 固定 `"1.0.0"` |
| `parse_id` | UUID | ✅ | 本次解析的唯一識別 |
| `company_id` | UUID | ✅ | 租戶隔離鍵 (遵循八律律三) |
| `idempotency_key` | String | ✅ | 冪等鍵 |
| `channel` | Enum | ✅ | `line` / `voice` / `web` |
| `locale` | Enum | ✅ | 五語系 (zh-Hant-TW, en-US, th-TH, ja-JP, id-ID) |
| `status` | Enum | ✅ | `PENDING_REVIEW` / `REJECTED` |
| `reason_code` | Enum | ✅ | `OK`, `LOW_CONFIDENCE`, `NO_ITEMS_PARSED` 等 |
| `confidence` | Float | ✅ | 0.0～1.0 |
| `currency` | String | ✅ | ISO-4217 (如 TWD) |
| `currency_exponent` | Integer | ✅ | TWD = 0, USD = 2 |
| `items` | Array | ✅ | 訂單品項草稿 |
| `metadata` | Metadata | ✅ | 解析元數據 (不含明文 raw_text) |
| `occurred_at` | DateTime | ✅ | UTC |
| `parsed_at` | DateTime | ✅ | UTC |

---

## 2. 核心裁決規則

1. **信心閾值 (Fail-closed)**: 信心值 < 0.85 一律標示為 `REJECTED` 與 `LOW_CONFIDENCE`。
2. **去識別化 (PII Redaction)**: `metadata` 嚴禁包含 `raw_text`。必須使用 `redacted_text`，原文僅保留在來源端。
3. **價格來源 (Catalog Authority)**: `unit_price_minor` 嚴禁由 LLM 產出，必須由型錄服務依 `resolved_sku` 填入。
4. **命名規範**: 統一使用 `company_id`，嚴禁使用 `tenant_id` 或其他別名以避免漂移。
5. **語音處理**: 本解析器僅處理文字，STT (語音轉文字) 需由獨立 Provider 處理。

---

## 3. 驗收標準 (AC)
- [ ] `unit_price_minor` 由型錄服務填入，LLM 僅產出 `raw_name` 與 `qty`。
- [ ] `metadata` 通過 Pydantic `extra="forbid"` 檢查，確保無明文洩漏。
- [ ] 0.84 信心值觸發 `REJECTED`，0.86 觸發 `PENDING_REVIEW`。
- [ ] 所有金額運算必須參考 `currency_exponent`。

