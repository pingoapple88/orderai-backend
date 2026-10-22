# OrderAI Baseline Lock 與品質治理政策

## 目的

本政策固定 OrderAI repository 的品質檢查命令與工具版本，讓每次分支都能與 `origin/main` 做可重播比較。它不把既有品質債誤標為新回歸，也不使用全域 ignore 讓 gate 假性變綠。

## 執行環境

```text
Python baseline runner：3.12.x
Ruff：0.16.9
mypy：2.3.1
pytest：9.1.1
pytest-asyncio：1.4.0
httpx（test client）：0.27.2
target runtime：Python >=3.9
```

`Python 3.12.x` 是目前 repository quality evidence 的固定執行環境；`requires-python >=3.9` 仍是產品相容範圍，不代表其他 Python 版本的品質數字可直接與本 baseline 比較。

## Repository policy

`pyproject.toml` 固定：

- Ruff `required-version = "==0.16.9"`
- Ruff target `py39`
- Ruff line length `88`
- Ruff rule selection：B008、B017、BLE001、DTZ011、F401、FA100、FURB157、I001、PLW1510、RUF022、TRY004、UP006、UP032、UP035、UP045
- mypy `python_version = "3.12"`，與固定的 baseline runner 相同
- mypy `files = ["app"]`
- mypy 顯示 error code，且啟用 unused config warning
- pytest `testpaths = ["tests"]` 與 `-ra`

Quality tool 與 test client 版本也列在 `[project.optional-dependencies].dev`；更新版本必須建立新的 baseline，不得直接覆蓋舊 evidence。

## 標準命令

在 repository root 執行：

```bash
python -m pytest -q
python -m ruff check app tests
python -m mypy app
python -m compileall -q app tests
python -m pytest --collect-only -q
```

要同時產生 `origin/main` 對照與 raw evidence：

```bash
python scripts/capture_quality_baseline.py \
  --repository . \
  --base-ref origin/main \
  --output /tmp/orderai-quality-baseline \
  --python .venv/bin/python \
  --alembic .venv/bin/alembic \
  --expected-python 3.12
```

此腳本只建立 detached temporary worktree、讀取本地原始碼並執行本地測試；不呼叫外部 API、不寫入資料庫、不連接 LINE、ERP、付款、發票或 Production。

## 分類語義

```text
BASELINE_REPRODUCED
  current 與 base 沒有新增 Ruff／mypy signature。

NEW_QUALITY_FAILURES
  current 出現 base 沒有的 Ruff／mypy signature，必須停止交付並修正或回報。

fixed
  current 不再出現 base 的 diagnostic；只能在明確 cleanup work item 中宣稱修正。

existing
  base 與 current 都存在的 diagnostic；不得標為新回歸。
```

比較以 `檔案相對路徑 | rule/error code | message` 作為 signature。行號變動不會被誤判為新問題；若訊息或 error code 改變，仍會列為 new／fixed，需人工檢視。

## 交付 Gate

OAI-Q0 只有在下列條件同時成立時才可標記綠燈：

- branch 與 rollback SHA 已記錄。
- `origin/main` detached baseline 可重現。
- current 與 base 的 pytest／compileall 均為 exit 0。
- `BASELINE_REPRODUCED`，或每個 new diagnostic 都有明確 owner／修正 work item。
- raw command、stdout、stderr、snapshot、comparison JSON 已保存。
- `git diff --check` 通過。
- secret／平台痕跡掃描通過。

目前的 428 Ruff、24 mypy errors 是歷史 baseline；OAI-Q0 不宣稱它們已修復。

## 禁止事項

- 不得使用 `--unsafe-fixes` 一次覆蓋全 repository。
- 不得新增全域 `ignore` 來消除既有診斷。
- 不得把 Q0 policy 變更與 WJ business logic 混成同一 commit。
- 不得因 pytest 通過就宣稱品質 debt 已解除。
- 不得把 baseline lock 當成正式 ERP、付款、發票、LINE 或 Production Gate。
