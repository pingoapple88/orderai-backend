# C6 Provider Gate Packet 001

> **Work item:** `C6-PROVIDER-GATE-PACKET-001`
> **用途：** 給 payment／invoice／ERP／LINE／device／平台／DR／Production reviewer 填寫與審查的 provider-neutral owner packet。
> **邊界：** 本文件只建立欄位、證據格式、停止條件與 reviewer handoff；不呼叫任何 provider、不登入、不讀正式資料、不使用 secrets、不付款、不退款、不做 ERP write、不開立發票、不操作設備、不 migration、不 deploy、不做 Production merge。

## 1. Packet identity and operating boundary

| 欄位 | 必填格式 | 本 work item 狀態 |
|---|---|---|
| `work_item_id` | 固定識別字串 | `C6-PROVIDER-GATE-PACKET-001` |
| `repository` | owner/repository | `pingoapple88/orderai-backend` |
| `branch` | Git branch | `docs/evidence` |
| `base_sha` | 40 字元 SHA-1 | `1ec667cb76e725d63f2a896077793bbd664b3ecd` |
| `head_sha` | 40 字元 SHA-1 | `ff60c614253ef254aec870ea81cc8c3de3f2a849` |
| `rollback_sha` | 可回復的既有 revision | `1ec667cb76e725d63f2a896077793bbd664b3ecd` |
| `mode` | `READ_ONLY` 或 `SYNTHETIC` | `READ_ONLY / SYNTHETIC` |
| `provider_call_count` | 本次工作實際呼叫數 | `0` |
| `formal_data_read` | 本次工作是否讀取正式資料 | `0` |
| `formal_data_write` | 本次工作是否寫入正式資料 | `0` |
| `production_deploy` | 本次工作是否部署 Production | `0` |
| `packet_owner` | 具名 owner、團隊與時區 | `[TODO: 待人工確認]` |
| `review_coordinator` | 具名 reviewer、團隊與時區 | `[TODO: 待人工確認]` |
| `decision` | `PENDING`／`PASS`／`FAIL`／`BLOCKED` | `PENDING` |

### 1.1 Non-negotiable boundary

1. 任何 endpoint、tenant、merchant、legal entity、tax rate、fee、credential、owner、設備識別、DNS record、TLS 憑證或 Production approval，若尚未由負責人提供並核對，欄位必須原樣保留 `[TODO: 待人工確認]`。
2. `SANDBOX`、`STAGING`、`ISOLATED_UAT`、`PRODUCTION` 不是可互換值；必須在 evidence 中明確標示 environment 與資料來源。
3. 只接受 provider-neutral contract 與可追溯 evidence；不能把單一 provider 的成功回應當作跨 provider 的能力保證。
4. 所有秘密只以 `credential_ref`、vault reference 或人工核准的 opaque identifier 表示；packet、log、screenshot、request／response、bundle 不得含 secret value、完整 token、私鑰或個資。
5. 任一 Gate 缺少 owner、環境、契約版本、可回復方案、redacted evidence 或 reviewer decision，維持 `BLOCKED`，不得升格。

## 2. Common owner packet schema

以下 YAML 是每個 domain packet 的最小資料契約。`[TODO: 待人工確認]` 是有意保留的人工欄位，不得以推測值替換。

```yaml
packet_schema_version: "C6-GATE-PACKET-v1"
work_item_id: "C6-PROVIDER-GATE-PACKET-001"
domain: "[TODO: 待人工確認]"
mode: "[TODO: 待人工確認]"
environment: "[TODO: 待人工確認]"
provider_name: "[TODO: 待人工確認]"
provider_account_ref: "[TODO: 待人工確認]"
legal_entity: "[TODO: 待人工確認]"
owner:
  name: "[TODO: 待人工確認]"
  team: "[TODO: 待人工確認]"
  contact_ref: "[TODO: 待人工確認]"
  timezone: "[TODO: 待人工確認]"
backup_owner: "[TODO: 待人工確認]"
endpoint_ref: "[TODO: 待人工確認]"
credential_ref: "[TODO: 待人工確認]"
contract_version: "[TODO: 待人工確認]"
source_revision: "[TODO: 待人工確認]"
correlation_id: "[TODO: 待人工確認]"
idempotency_key_rule: "[TODO: 待人工確認]"
rollback_plan_ref: "[TODO: 待人工確認]"
evidence:
  - evidence_id: "[TODO: 待人工確認]"
    captured_at_utc: "[TODO: 待人工確認]"
    artifact_path: "[TODO: 待人工確認]"
    sha256: "[TODO: 待人工確認]"
    redaction: "secret_and_personal_data_removed"
    observed_result: "[TODO: 待人工確認]"
    reviewer: "[TODO: 待人工確認]"
    decision: "PENDING"
stop_conditions:
  - "missing_owner"
  - "missing_environment_or_endpoint_confirmation"
  - "missing_contract_or_idempotency_rule"
  - "missing_redacted_evidence"
  - "missing_rollback_or_approval"
review:
  reviewer: "[TODO: 待人工確認]"
  decision: "PENDING"
  reviewed_at_utc: "[TODO: 待人工確認]"
  comments_ref: "[TODO: 待人工確認]"
```

### 2.1 Evidence record format

每一筆證據使用以下欄位；`artifact_path` 只能指向去識別、去 secret 的檔案。若證據不存在，仍建立 record 並以 `[TODO: 待人工確認]` 表示，不得填寫虛構路徑或 hash。

| 欄位 | 必填規則 |
|---|---|
| `evidence_id` | 唯一、不可重用；格式建議 `<domain>-<sequence>`，實際 sequence `[TODO: 待人工確認]` |
| `mode` | `READ_ONLY`、`SYNTHETIC`、`SANDBOX`、`ISOLATED_UAT`、`PRODUCTION_APPROVAL` 之一；未確認時 `[TODO: 待人工確認]` |
| `captured_at_utc` | ISO-8601 UTC；不能只寫本地時間 |
| `source_revision` | 受測程式、設定或契約的完整 revision |
| `artifact_path` | repository-relative 或受控 evidence store path；不能是個人電腦暫存路徑 |
| `sha256` | artifact 原檔 SHA-256；未產生時 `[TODO: 待人工確認]` |
| `redaction` | 明確寫出 secret、個資、付款資料與設備識別的處理結果 |
| `input_fixture_ref` | synthetic fixture 或核准的 UAT case；正式資料不可直接附入 |
| `observed_result` | 原始結果的去識別摘要；不能只寫「成功」 |
| `negative_case_result` | 至少一個 fail-closed／拒絕／重播案例的結果；若尚未執行 `[TODO: 待人工確認]` |
| `reviewer` | reviewer identity/team/timezone；未確認 `[TODO: 待人工確認]` |
| `decision` | `PENDING`、`PASS`、`FAIL`、`BLOCKED`，含判斷依據引用 |

建議的 evidence index JSON（內容必須經 redaction）：

```json
{
  "evidence_id": "[TODO: 待人工確認]",
  "domain": "[TODO: 待人工確認]",
  "mode": "[TODO: 待人工確認]",
  "environment": "[TODO: 待人工確認]",
  "source_revision": "[TODO: 待人工確認]",
  "captured_at_utc": "[TODO: 待人工確認]",
  "artifact_path": "[TODO: 待人工確認]",
  "sha256": "[TODO: 待人工確認]",
  "redaction": {
    "secrets_removed": true,
    "personal_data_removed": true,
    "payment_data_removed": true,
    "device_identifiers_removed": true
  },
  "observed_result": "[TODO: 待人工確認]",
  "negative_case_result": "[TODO: 待人工確認]",
  "reviewer": "[TODO: 待人工確認]",
  "decision": "PENDING",
  "comments_ref": "[TODO: 待人工確認]"
}
```

## 3. Payment / refund gate

### 3.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `payment_provider` | provider 名稱、版本、環境與 account reference | owner 提供的核准紀錄；不放 token |
| `merchant_owner` | merchant owner、營運團隊與 backup owner | owner acknowledgment；未確認 `[TODO: 待人工確認]` |
| `legal_entity` | 收款／退款所屬法人與核准 reference | finance／legal evidence；不得猜測 |
| `merchant_account_ref` | opaque account reference，不是帳號密碼 | redacted account confirmation |
| `endpoint_ref` | 明確區分 sandbox／staging；host、path、TLS trust source | provider-approved config evidence；未確認 `[TODO: 待人工確認]` |
| `credential_ref` | secret store reference、scope、expiry、rotation owner | 只留 reference；禁止 secret value |
| `operation_matrix` | authorize／capture／query／refund／partial refund／webhook／reconciliation 的支援狀態 | 每一 operation 的 synthetic 或核准 sandbox record |
| `amount_currency_rule` | 金額單位、幣別、四捨五入、最小單位與 overflow 行為 | contract／test fixture；金額規則未確認 `[TODO: 待人工確認]` |
| `fee_rule` | 費率、固定費、退款費與承擔方 | finance 核准文件；不得自行填值 |
| `idempotency_rule` | create、refund、retry、timeout、未知結果的 key 與 TTL | replay／duplicate fixture 結果 |
| `refund_authority` | 可退款角色、期限、部分退款與雙人覆核規則 | approval matrix；未確認 `[TODO: 待人工確認]` |
| `webhook_auth_and_replay` | signature、timestamp、nonce、replay window、事件去重 | redacted signature verification evidence |
| `ledger_reconciliation` | OrderAI order、payment intent、refund、settlement、ledger 的 correlation | synthetic reconciliation report |
| `failure_mapping` | timeout、decline、duplicate、unknown、provider outage 的 fail-closed mapping | negative-case evidence |
| `rollback_plan_ref` | 未知付款結果、重複退款、對帳差異的人工處理 runbook | reviewer-approved runbook reference |

### 3.2 Stop conditions

- 沒有 provider-approved sandbox／staging environment、owner、merchant legal entity 或 credential scope。
- 金額、幣別、費率、退款授權、結算週期或稅務歸屬尚未由 finance／legal 確認。
- 沒有 idempotency、replay protection、未知結果處理或 immutable audit evidence。
- 任何測試會產生真實扣款、退款、charge、settlement 或正式 webhook。
- provider 回傳與內部 ledger／order 狀態無法一對一追蹤，或 reconciliation 有未解差異。
- reviewer 尚未簽署 `PASS`；此 Gate 保持 `BLOCKED`，不執行付款或退款。

### 3.3 Reviewer handoff

Owner 交付：填妥 payment packet、redacted request／response、positive 與 negative replay evidence、對帳摘要、退款授權、rollback runbook。Finance reviewer 核對法人／幣別／費率／對帳；Security reviewer 核對 credential scope／signature；C6 reviewer 只核對 contract、狀態機與 fail-closed，不替任何人推定商務或稅務欄位。

## 4. Invoice / accounting / tax gate

### 4.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `invoice_issuer` | 開票法人、分支或營業主體與 authority | finance／legal written approval |
| `tax_registration_ref` | 稅籍／登記 reference（可遮罩） | 核准文件；不得放完整敏感識別 |
| `invoice_numbering_rule` | 字軌、號碼範圍、年度／期別、重號處理 | accounting rule + synthetic sequence test |
| `tax_regime` | 適用稅制與交易類型 | tax owner sign-off；未確認 `[TODO: 待人工確認]` |
| `tax_rate` | 逐 SKU／服務類型稅率與生效日期 | tax authority／finance evidence；不得猜測任何稅率 |
| `tax_inclusive_rule` | 含稅／未稅、稅額拆分、四捨五入與差額歸屬 | signed accounting rule + fixtures |
| `item_account_mapping` | SKU／收入科目／稅碼／成本中心／營業單位 mapping version | versioned mapping artifact |
| `credit_note_refund_rule` | 退款、折讓、折讓單／作廢與原發票關聯 | accounting workflow + negative case |
| `invoice_trigger` | 付款、交付、訂單完成或其他觸發事件 | contract and state transition evidence |
| `invoice_provider_ref` | provider account、environment、endpoint、credential reference | redacted config; values remain TODO until confirmed |
| `accounting_period` | 會計期間、cut-off、補開／跨期規則 | controller approval |
| `retention_and_export` | 保存年限、可稽核匯出格式、access owner | policy reference; no formal records in this packet |
| `reconciliation_owner` | 發票、payment、refund、GL 的日／月對帳 owner | signed responsibility matrix |
| `legal_disclaimer` | 稅務／法律文字的核准版本與生效日期 | legal/tax approval; not authored by this packet |

### 4.2 Stop conditions

- 法人、稅籍、稅制、稅率、費率、發票觸發點、科目 mapping 或保存政策未核准。
- 沒有 sequence uniqueness、重送冪等、折讓／作廢／退款關聯與 audit trail。
- 任何測試會開立真實發票、傳送正式電子發票、申報、改寫正式帳務或跨期帳。
- 會計 reviewer 與 tax／legal reviewer 的結果不一致，或 evidence 缺少 source revision／hash。
- 任何稅務結論只是工程團隊推測；立即標為 `BLOCKED` 並交回 tax owner。

### 4.3 Reviewer handoff

Owner 交付：法人／稅籍核准、mapping version、synthetic invoice／credit-note fixtures、sequence 與 rounding 測試、payment-to-invoice-to-ledger reconciliation、retention／export proof。Accounting reviewer、tax reviewer、legal reviewer 分別留下 decision；C6 不替 reviewer 決定稅率、費率、法人或法定文字。

## 5. Yunding / Jiezhou ERP staging gate

### 5.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `erp_system` | `Yunding` 或 `Jiezhou` 及明確 system role | owner-provided system inventory |
| `erp_environment` | `STAGING`／`ISOLATED_UAT`；禁止以 production 值代替 | environment attestation |
| `staging_endpoint_ref` | host／path／TLS trust／allowlist reference | provider or IT-approved config；未確認 `[TODO: 待人工確認]` |
| `tenant_company_site_ref` | tenant、company、site、warehouse 等 scope reference | masked mapping approval；不得猜測 |
| `principal_ref` | staging principal、RBAC scope、expiry、rotation owner | access review；禁止 credential value |
| `adapter_contract_version` | request／response schema、error mapping、idempotency version | versioned contract artifact |
| `mapping_version` | SKU、unit、warehouse、customer、tax、payment status 等 mapping | synthetic fixture hash + mapping approval |
| `operation_matrix` | read／validate／dry-run／submit／retry／cancel 的允許狀態 | capability matrix；write 必須明確為 `NOT_ENABLED` 或核准狀態 |
| `write_boundary` | staging write 是否允許、誰批准、何時失效 | explicit written approval；預設 fail-closed |
| `payload_classification` | synthetic、masked UAT 或其他核准資料分類 | fixture source attestation |
| `replay_and_idempotency` | external reference、dedupe、retry、unknown-result handling | duplicate／timeout test evidence |
| `erp_audit_reference` | request／response correlation、provider receipt、internal audit link | redacted evidence index |
| `rollback_or_compensation` | 送件失敗、部分成功、未知狀態的人工處理 | approved runbook; no automatic production repair |
| `provider_support_owner` | Yunding／Jiezhou support owner、response window、escalation | owner acknowledgment |

### 5.2 Stop conditions

- staging endpoint、tenant／company／site scope、principal 或 RBAC 未經 IT owner 核准。
- 不能證明資料是 synthetic／masked UAT，或 payload 含正式會員、訂單、財務或個資。
- mapping、契約版本、幂等規則、錯誤分類或 receipt correlation 未完成。
- 任一流程需要正式 ERP write、正式 migration、正式庫存／訂單／發票更新或未核准的 compensating action。
- Yunding 與 Jiezhou 的 capability／mapping 不同但未拆成獨立 packet；不得用一個成功案例代表另一個系統。

### 5.3 Reviewer handoff

ERP owner 交付 staging attestation、scope/RBAC、contract／mapping version、synthetic payload、positive／negative／replay evidence 及人工 rollback runbook。IT reviewer 核對 endpoint／身份／網路；業務 owner 核對欄位 mapping；C6 只核對 adapter boundary、idempotency、audit 與 stop conditions。任何 write enablement 都必須另建人工 decision，不由本 packet 自動解除。

## 6. LINE / OrderAI gate

### 6.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `line_channel_ref` | channel／bot／provider account opaque reference | owner attestation; no token |
| `line_environment` | test／staging／isolated UAT／production | environment proof |
| `webhook_endpoint_ref` | verified host/path、TLS、allowlist與 routing reference | approved configuration; 未確認 `[TODO: 待人工確認]` |
| `signature_verification` | signature algorithm／key reference／timestamp／replay window | redacted verification fixture |
| `liff_or_client_ref` | client／LIFF reference、version、redirect policy | release/config evidence |
| `orderai_contract_version` | inbound event、order state、manual confirmation、outbox/event schema | contract artifact |
| `consent_and_pii_policy` | 使用者同意、最小化、masking、retention、deletion owner | privacy/security approval |
| `event_idempotency` | event ID、dedupe、retry、out-of-order handling | replay／duplicate fixture |
| `message_policy` | outbound message categories、template approval、rate limit、failure handling | synthetic dispatch evidence; no real message |
| `manual_review_boundary` | 低信心、未知商品、未知付款、未知 delivery 狀態如何轉人工 | negative-case evidence |
| `line_owner_and_support` | channel owner、OrderAI owner、客服／incident escalation | owner matrix |
| `credential_ref` | secret reference and least privilege | access review; no values |

### 6.2 Stop conditions

- webhook host、channel owner、signature key reference、environment 或 consent policy 未確認。
- 測試會接收或發送真實使用者訊息、建立真實訂單、觸發付款／退款或改寫正式庫存。
- 事件去重、重播防護、低信心人工覆核、PII redaction 或 outbox audit 缺失。
- LINE event、OrderAI order、payment／ERP correlation 無法追蹤，或 retry 可能重複下單／通知。
- 未完成 channel／客服 owner handoff；不得把 `/health` 或單次 synthetic parser 測試當作 end-to-end approval。

### 6.3 Reviewer handoff

LINE owner 交付 test channel attestation、redacted signature/replay fixtures、message template approval、consent／PII review、OrderAI contract revision 與人工 fallback proof。OrderAI owner 核對狀態機、outbox、audit、idempotency；security/privacy reviewer 核對最小權限與資料處理；C6 維持 provider-neutral boundary。

## 7. iMin / device gate

### 7.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `device_provider_and_model` | iMin 型號、firmware、SDK／protocol version | owner-provided inventory |
| `device_ref` | masked serial／asset reference、site／store scope | asset record；不得附完整敏感 identifier |
| `device_owner` | 設備、門市、補貨、故障、客服責任 owner | RACI acknowledgment |
| `device_environment` | lab／test store／isolated UAT／production | environment attestation |
| `network_and_pairing` | network segment、pairing／enrollment method、allowlist | IT/device approval; no secrets |
| `command_matrix` | status／health／payment display／print／open-door／dispense 等能力與允許狀態 | capability matrix; 不可推定型號能力 |
| `safety_boundary` | 不開門、不出貨、不扣庫、不改正式狀態的測試限制 | signed test plan |
| `device_auth_ref` | certificate／key／credential opaque reference、expiry、rotation owner | access review |
| `timeout_and_unknown` | timeout、斷線、部分成功、未知結果與人工處置 | fail-closed replay evidence |
| `telemetry_and_audit` | device event、order reference、operator、timestamp、correlation | redacted event evidence |
| `maintenance_and_rollback` | firmware／config rollback、現場責任、停用方式 | approved runbook |
| `test_window` | 時段、現場負責人、停止信號與 incident contact | change/test approval |

### 7.2 Stop conditions

- 型號、firmware、protocol、asset owner、site、network、pairing 或 safety plan 未確認。
- 測試可能開門、出貨、扣庫、扣款、補發或改寫正式訂單／會員／點數。
- timeout 或 unknown result 沒有 fail-closed、人工任務與 audit correlation。
- 沒有現場 owner、測試時段、緊急停止與可回復 config；不得以模擬成功替代實機核准。
- 裝置能力與 iMin／device contract 不一致，或 supplier support 尚未承認版本。

### 7.3 Reviewer handoff

Device owner 交付 masked asset inventory、lab/test attestation、capability matrix、safety test plan、timeout／unknown evidence、maintenance／rollback runbook。IT reviewer 核對 network／identity；營運 owner 核對現場責任；C6 只核對 event／order correlation 與 fail-closed boundary。任何 production door／dispense／stock action 都需要獨立人工 Gate。

## 8. Railway / DNS / TLS gate

### 8.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `platform_project_ref` | Railway project／service／environment opaque reference | platform owner attestation |
| `deployment_source` | repository、branch/tag、commit、build artifact digest | CI/build evidence |
| `deployment_approver` | release owner、reviewer、change reference | approval record |
| `runtime_config_ref` | non-secret config revision；secret refs only | redacted config diff |
| `hostname_ref` | intended hostname、environment、service binding | DNS/platform approval; 未確認 `[TODO: 待人工確認]` |
| `dns_zone_owner` | zone owner、record change authority、TTL policy | DNS owner approval |
| `dns_record_set` | record type、target ref、TTL、change window | redacted DNS change evidence |
| `tls_certificate_ref` | certificate issuer/ref、SAN scope、expiry、renewal owner | certificate metadata only; no private key |
| `tls_policy` | minimum protocol/cipher policy、redirect、HSTS decision | security approval |
| `health_and_readiness` | health、readiness、dependency checks、alert owner | synthetic/isolated evidence |
| `rollback_revision` | prior known-good commit/artifact、rollback command owner、verification | rollback drill evidence |
| `observability` | logs、metrics、traces、alert routing、retention | monitoring evidence |
| `change_window` | UTC window、maintenance notice、abort signal | change approval |

### 8.2 Stop conditions

- project/service/environment、deployment source、hostname、DNS zone owner 或 TLS certificate scope 未確認。
- 需要 Production deploy、DNS write、TLS issuance／renewal、secret rotation 或 billing／ownership change。
- 健康檢查沒有區分 application、database、provider dependency；或 rollback 未在隔離環境驗證。
- certificate expiry、SAN、renewal owner 或 alert route 未能提供可核對 evidence。
- 任何 temporary URL、管理 URL 或秘密出現在 packet、log、screenshot 或 public handoff。

### 8.3 Reviewer handoff

Platform owner 交付 project/service/env、build digest、runtime config diff、DNS／TLS metadata、health／observability evidence 與 rollback drill。Security reviewer 核對 TLS／secret reference／公開面；release reviewer 核對 source provenance、change window、abort／rollback；C6 不執行 deploy、DNS write 或 Production merge。

## 9. Backup / DR gate

### 9.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `protected_scope` | DB、object、config、audit、outbox、evidence 的明確 scope | inventory and classification |
| `backup_owner` | backup operator、service owner、escalation owner | signed RACI |
| `schedule_and_retention` | schedule、retention、legal hold、deletion authority | approved policy；未確認 `[TODO: 待人工確認]` |
| `backup_location_ref` | region／storage target opaque ref、access boundary | storage attestation; no public link |
| `encryption_and_key_owner` | at-rest／in-transit、key reference、rotation owner | security evidence; no key values |
| `backup_artifact_ref` | run ID、captured UTC、size/classification、SHA-256 | backup manifest |
| `restore_environment` | isolated restore target、network boundary、owner | restore approval |
| `rpo_rto` | RPO、RTO、measurement clock與business owner | approved continuity decision; no guessed values |
| `restore_validation` | schema／row count／checksum／audit／PII isolation validation | restore test report |
| `application_recovery` | worker、outbox、scheduler、provider dependency recovery order | runbook and synthetic drill |
| `failover_and_abort` | failover trigger、abort、read-only mode、manual decision | DR exercise evidence |
| `last_verified_at` | latest restore verification timestamp and revision | signed report |
| `data_handling` | no formal data in packet; redaction and deletion proof | evidence index |

### 9.2 Stop conditions

- 沒有 backup owner、scope、retention、encryption/key owner 或 restore owner。
- backup artifact 無完整 SHA-256、不可讀、不可在隔離環境 restore，或 restore 會觸碰正式資料。
- RPO／RTO 未由 business／technology owner 核准；不得由工程團隊猜測。
- restore validation 未證明 schema、audit、outbox、權限與 PII isolation；不能只看檔案存在。
- failover／abort／rollback 沒有明確人工 decision；不得自動切換 Production。

### 9.3 Reviewer handoff

Backup/DR owner 交付 redacted backup manifest、checksum、隔離 restore report、RPO/RTO approval、runbook 與最近 verification。Security reviewer 核對 encryption/access；technology owner 核對可恢復性；business owner 核對 continuity decision；C6 只引用 evidence，不接觸正式資料或秘密。

## 10. Production approval gate

### 10.1 Mandatory fields

| 欄位 | 必填內容 | 證據要求 |
|---|---|---|
| `release_revision` | exact commit、artifact digest、source provenance | immutable build evidence |
| `scope_and_change_summary` | affected domains、API／contract／data impact | reviewed change note |
| `test_exit` | focused、regression、security、contract、rollback／restore test result | raw stdout/stderr + result index |
| `provider_readiness` | each provider domain 的 owner、environment、contract、evidence、decision | linked domain packets |
| `data_and_migration_impact` | schema／migration／backfill／formal data impact | migration review; if unknown `[TODO: 待人工確認]` |
| `observability_ready` | dashboards、alerts、log redaction、on-call、freshness checks | monitoring evidence |
| `security_ready` | secret scan、dependency scan、access review、TLS review | scan reports with hashes |
| `backup_and_rollback_ready` | backup verification、rollback revision、abort owner、recovery window | linked DR/release evidence |
| `legal_finance_approval` | payment／invoice／tax／entity decisions as applicable | signed approvals; no inference |
| `change_window` | UTC window、communication、abort threshold | change record |
| `approver_matrix` | engineering、security、operations、finance/tax/legal、business owner | named decisions; TODO if missing |
| `go_no_go` | decision、timestamp、decision owner、unresolved risks | final approval record |
| `post_release_verification` | health、business reconciliation、provider callback、audit and rollback observation | post-release checklist |

### 10.2 Stop conditions

- 任一 domain packet 為 `PENDING`、`FAIL`、`BLOCKED` 或缺少 reviewer decision。
- source provenance、focused test、security scan、backup／rollback、observability 或 incident owner 缺失。
- payment、invoice、tax、ERP write、device action、DNS/TLS、secret、migration 或正式資料的人工 Gate 尚未明確通過。
- change window、abort threshold、rollback owner 或 post-release verification 未核准。
- 任何人要求以「測試環境成功」、「branch 已存在」或「health endpoint 正常」代替 Production approval。

### 10.3 Reviewer handoff

Release owner 只能在所有 linked evidence 可讀、hash 可核對、reviewer decision 完整後提出 `GO`。各 domain owner 對自己的商務／法遵／營運結論負責；security、finance/tax/legal、operations、business 與 engineering 必須留下獨立 decision。C6 reviewer 只做整合檢查與 `READY_FOR_REVIEW` handoff，不自行批准 Production。

## 11. Cross-chat status and reviewer handoff record

本 work item 完成文件交付時，使用以下 durable status；不得宣稱已直接私訊其他 Team。若無 connector，將此區塊連同 evidence index 交給 coordinator，由 coordinator 更新 canonical shared index；本文件本身不修改 shared queue／manifest／roster。

```text
CROSS_CHAT_STATUS_UPDATE
work_item: C6-PROVIDER-GATE-PACKET-001
team: C6 Integration Gate
stream_id: C6-PROVIDER-GATE-PACKET-001
status: READY_FOR_HANDOFF
mode: READ_ONLY / SYNTHETIC
repository: pingoapple88/orderai-backend
branch: docs/evidence
base_sha: 1ec667cb76e725d63f2a896077793bbd664b3ecd
head_sha: ff60c614253ef254aec870ea81cc8c3de3f2a849
parent_sha: 1ec667cb76e725d63f2a896077793bbd664b3ecd
rollback_sha: 1ec667cb76e725d63f2a896077793bbd664b3ecd
changed_paths: [docs/gates/c6-provider-gate-packet-001.md, scripts/validate_c6_provider_gate_packet.py, tests/test_c6_provider_gate_packet.py]
input_evidence: /home/ubuntu/projects/merchcore-stallpay-e5845ba0/MERCHCORE_STALLPAY_PARALLEL_WORK_DISPATCH_2026-10-17.md
output_evidence: [TODO: 待人工確認]
focused_test_exit_code: [TODO: 待人工確認]
stdout_path: [TODO: 待人工確認]
stderr_path: [TODO: 待人工確認]
related_teams: C1 StallPay; C5 Shared Core; T8 ERP; T9 Finance
cross_chat_request: 各 owner 以本 packet 建立自己的 redacted evidence 與 reviewer decision；不得解除正式 Gate。
blocker: provider／owner／credential／Production evidence 尚未提供；本 work item 不執行外部動作。
decision_required: yes
user_action_required: yes
next_action: owner 填 packet → reviewer 核 evidence → coordinator 只 review 新 revision → Production approval 維持獨立人工 Gate
```

### 11.1 Affected-team acknowledgement template

```text
CROSS_CHAT_ACK
work_item: C6-PROVIDER-GATE-PACKET-001
from_team: [TODO: 待人工確認]
to_team: C6 Integration Gate
input_revision: [TODO: 待人工確認]
input_evidence: [TODO: 待人工確認]
accepted: no
missing: owner、environment、redacted evidence、reviewer decision、rollback/approval references
next_exit: submit one complete domain packet with evidence index and SHA-256
user_action_required: yes
```

## 12. Delivery checklist and explicit next exit

- [x] 僅一份 Gate packet 文件新增於 `docs/gates/`；沒有修改 canonical shared queue／manifest／roster。
- [x] 欄位採 provider-neutral 命名；未確認值保留 `[TODO: 待人工確認]`。
- [x] 覆蓋 payment/refund、invoice/accounting/tax、Yunding/Jiezhou ERP staging、LINE/OrderAI、iMin/device、Railway/DNS/TLS、backup/DR、Production approval。
- [x] 每個 domain 都有 mandatory fields、evidence format、stop conditions 與 reviewer handoff。
- [x] 明確禁止 provider call、登入、secret、正式資料、付款、ERP write、發票、設備、migration、deploy 與 Production merge。
- [x] 必須通過 Markdown／YAML syntax、diff、secret/platform-shadow scan，以及 packet validator/test。
- [x] 必須保存 raw stdout/stderr、changed paths、commit SHA 與 rollback bundle。

**Single next exit：** `[TODO: 待人工確認]` owner 逐 domain 填入核准的 environment／owner／contract／evidence reference；在所有 reviewer decision 為 `PASS` 前，整體狀態保持 `BLOCKED`，不得執行任何正式 provider 或 Production 動作。
