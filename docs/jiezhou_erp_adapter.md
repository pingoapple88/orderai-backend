# 捷州 ERP 待確認訂單 Adapter（Issue #39）

本文件定義 **Jiezhou P0** 的受控合成驗收邊界。實作延伸既有 `IErpIngestProvider`，並以 provider-neutral `PendingOrderIntent` 表示待確認訂單；沒有在其他 repository 建立第二套 ingest 介面，也沒有沿用任何其他 ERP 的 endpoint、欄位、錯誤碼、company／sales-location ID 或憑證。

## 安全狀態與 provider 選項

`JIEZHOU_ERP_INGEST_PROVIDER=blocked` 是預設值。設定為 `jiezhou` 表示未來正式 adapter 的選擇意圖，仍必須同時具備非秘密的 tenant、company、sales location、product mapping 與契約參照；任一值遺漏、格式無效或範圍不符時，factory 仍回傳 blocked provider。即使這些設定完整，本 PR 的 `JiezhouBlockedErpIngestProvider` 仍一律回覆 `ERP_CONNECTION_BLOCKED`，因為下列正式資訊都是 **[TODO: 待人工確認]**，且本 PR 不含 HTTP client、endpoint、認證或任何外部呼叫。

```dotenv
# 捷州 ERP：僅合成契約／正式 adapter 選擇意圖；預設 fail-closed。
JIEZHOU_ERP_INGEST_PROVIDER=blocked
JIEZHOU_TENANT_ID=0
JIEZHOU_COMPANY_ID=0
JIEZHOU_SALES_LOCATION_ID=0
JIEZHOU_PRODUCT_MAPPING_JSON={}
JIEZHOU_CONTRACT_REFERENCE=
```

上列為安全 placeholder，並非真實租戶、公司、據點、商品或憑證。不得把其值替換為從其他 ERP 取得的資料。`jiezhou_fake` 僅供測試程式顯式注入，不能由環境設定啟用，且沒有網路傳輸功能。

## 共通契約與合成 fixture

`PendingOrderIntent` 只含：tenant、company、sales location、source event、五欄內容（buyer name、受控 contact reference、requested-for、special request、items）、商品 mapping、idempotency key 與 audit reference。它刻意排除 payment、inventory、shipment、invoice 與 formal order 欄位。

合成 fixture 位於 `tests/fixtures/jiezhou_pending_order_contract_v1.json`，版本為 `jiezhou-pending-order-synthetic-v1`；內容均為 synthetic 值，且標記 `contract_status: [TODO: 待人工確認]`。deterministic fake 僅建立 `pending` 或 `manual_review` 結果；相同 idempotency key 回傳同一結果。缺 mapping、company／sales-location scope 不符、timeout 或 unknown outcome 都進 manual review，不建立任何正式交易副作用。

## 捷州 owner 最小契約輸入清單

在實作任何非 blocked transport 前，捷州業務／技術 owner 必須以書面提供 sandbox，而非正式環境的：(1) API base URL 與 route；(2) 認證機制、service identity 與 secret 交付管道；(3) request／response schema、必填與可選欄位、型別和 enum；(4) pending、rejected、manual-review、timeout、unknown 的錯誤碼與重試語義；(5) tenant、company、sales-location 的正式對應與授權範圍；(6) 商品 mapping 的來源、版控與未映射處理；(7) idempotency scope／保存期與 audit correlation 規格；以及 (8) sandbox 測試資料處理與驗收 owner。缺任一項均維持 `ERP_CONNECTION_BLOCKED`。

## 容器、migration 與 rollback

`Dockerfile` 與 `docker-compose.yml` 不需新增 adapter runtime service 或網路設定：Jiezhou production adapter 沒有 transport，且 compose 不會注入任何 Jiezhou endpoint／secret。本次為純 Python contract、factory、fake、fixture 與測試變更，**migration not required**；未建立、未執行 migration，也未接觸正式資料或正式 ERP。

部署前 rollback 是保留的前一個 SHA `1ec667cb76e725d63f2a896077793bbd664b3ecd`。若此 PR 已部署，rollback 方法為 revert 本 PR 的單一 commit，並回復至該部署前 SHA；不得執行資料 rollback、正式 migration 或任何外部 ERP 補償呼叫。

## 主權檢核

1. 變更僅會推送至 `pingoapple88/orderai-backend` 的受控 feature branch。
2. 沒有新增非官方 CDN、追蹤碼、telemetry 或外部網路依賴。
3. Git 作者固定為 `pingoapple88 <pingoapple88@users.noreply.github.com>`。
4. 未包含平台特定執行期依賴或產生器痕跡。
5. 未複製或引用其他 ERP 的 URL、憑證、company／sales-location ID、欄位或錯誤碼。
6. fake fixture 與 focused tests 全為合成資料；未連接捷州正式 ERP、未部署、未執行正式 migration。
7. 正式 adapter 在未知契約、缺設定與設定完整時都 fail-closed；所有異常結果維持 manual review，且無付款、庫存、出貨、發票或正式訂單副作用。
