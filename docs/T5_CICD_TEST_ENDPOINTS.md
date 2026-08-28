# T5 OrderAI CI/CD 測試接點

> 此文件只描述 feature branch 的 synthetic／Mock 驗證接點；不連接正式 LLM、LINE、Queue、資料庫、支付或金鑰。

## 執行入口

```bash
python3 ci/t5_orderai_ui_checks.py --output evidence/t5_cicd_entrypoint_manifest.json
```

入口會實際執行不需資料庫的 strict quantity、Unicode 離線評測、五語系契約、OrderAI UI focused pytest 與既有 Demo contract，接著執行 `compileall`、working-tree diff check，以及 local screen assets 的 runtime／PII／tenant-scope 掃描。成功時退出碼為 `0`，輸出 `T5-CICD-EVIDENCE-01` JSON manifest；任一檢核失敗即 fail-closed。

## 交接欄位

| 欄位 | T5 實際值 |
|---|---|
| `fixture_path` | `src/ui/fixtures/orderai/orderai_screen_scenarios.json` |
| `screen_contract_version` | `ORDERAI-UI-W2-01` |
| `harness_path` | `tests/ui/orderai/test_orderai_ui_harness.py`、`tests/ui/orderai/test_orderai_screen_renderer.py`、`tests/ui/orderai/test_t5_cicd_entrypoint.py` |
| `required_env_names_only` | `[]`；此接點無需環境變數。 |
| `expected_exit_code` | test、compile、diff check、scan 均為 `0`。 |
| `evidence_paths` | `evidence/t5_cicd_entrypoint_manifest.json`、`evidence/t5_cicd_entrypoint_run.log`。 |
| `rollback_reference` | 執行時由 Git `HEAD^` 寫入 manifest。 |

## CI workflow

`.github/workflows/t5-orderai-ui-checks.yml` 僅在 `feat/t5-*` branch、匹配路徑的 Pull Request 或手動觸發執行。workflow 權限固定為 `contents: read`，不讀取 repository secret、不自動 merge、部署或寫入 main；artifact 僅保存 redacted JSON manifest 14 天。

## 已知待辦

完整 `pytest -q` 仍受既有可丟棄資料庫／Alembic 前置與 inherited OAuth state-cookie baseline blocker 影響，保持由獨立 PR #22 解鎖。T5 接點不 cherry-pick、複製或修改 Auth 測試；R1 應以 `open_todos` 欄位判讀此隔離狀態。T1 尚需接入 T5 local renderer、CSS、interaction 與 fixture，並提供瀏覽器驗證 evidence。
