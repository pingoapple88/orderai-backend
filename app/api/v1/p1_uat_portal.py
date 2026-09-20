"""青泉谷 P1 staging synthetic UAT Portal HTML 與 JSON API。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.response import success_response
from app.services import p1_uat_portal_service

router = APIRouter()
_http_basic = HTTPBasic(auto_error=False)


class _PortalModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class P1UatPortalCaseCreate(_PortalModel):
    buyer_alias: str = Field(min_length=1, max_length=120)
    product_name: str = Field(min_length=1, max_length=255)
    quantity: int = Field(ge=1, le=99)
    requested_for: str = Field(min_length=1, max_length=120)
    special_requirement: str = Field(min_length=1, max_length=1000)


def _portal_auth_denied() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="P1 UAT portal operator authentication required",
        headers={"WWW-Authenticate": 'Basic realm="P1 staging UAT"'},
    )


def _require_portal_operator(
    credentials: HTTPBasicCredentials | None = Depends(_http_basic),
) -> None:
    """Portal page 與 JSON action 共用的 operator Basic Auth，預設拒絕。"""
    settings = get_settings()
    expected_username = settings.p1_uat_portal_basic_username
    expected_password = settings.p1_uat_portal_basic_password
    username_matches = p1_uat_portal_service.constant_time_secret_equals(
        credentials.username if credentials else "", expected_username
    )
    password_matches = p1_uat_portal_service.constant_time_secret_equals(
        credentials.password if credentials else "", expected_password
    )
    if not (
        settings.p1_uat_portal_enabled
        and expected_username
        and expected_password
        and credentials
        and username_matches
        and password_matches
    ):
        raise _portal_auth_denied()


def _require_portal_page_environment() -> None:
    try:
        p1_uat_portal_service.assert_portal_environment()
    except p1_uat_portal_service.P1UatPortalBlocked as exc:
        raise HTTPException(403, "P1 UAT portal environment denied") from exc


def _require_portal_access(
    response: Response,
    access_code: Annotated[
        str | None,
        Header(alias="X-P1-UAT-Access-Code"),
    ] = None,
) -> None:
    try:
        p1_uat_portal_service.assert_portal_access(access_code)
    except p1_uat_portal_service.P1UatPortalBlocked as exc:
        raise HTTPException(403, "P1 UAT portal access denied") from exc
    response.headers["Cache-Control"] = "no-store"


def _run_portal_action(action):
    try:
        return success_response(action())
    except p1_uat_portal_service.P1UatPortalNotFound as exc:
        raise HTTPException(404, "Synthetic UAT case not found") from exc
    except p1_uat_portal_service.P1UatPortalConflict as exc:
        raise HTTPException(409, "Synthetic UAT case is not reviewable") from exc
    except p1_uat_portal_service.P1UatPortalBlocked as exc:
        raise HTTPException(403, "P1 UAT portal synthetic scope denied") from exc


@router.get(
    "/uat/p1",
    response_class=HTMLResponse,
    dependencies=[Depends(_require_portal_operator), Depends(_require_portal_page_environment)],
    include_in_schema=False,
)
def p1_uat_portal_page() -> HTMLResponse:
    return HTMLResponse(
        content=_PORTAL_HTML,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get(
    "/api/v1/uat/p1/status",
    dependencies=[Depends(_require_portal_operator), Depends(_require_portal_access)],
)
def p1_uat_portal_status(db: Session = Depends(get_db)):
    return _run_portal_action(lambda: p1_uat_portal_service.portal_status(db))


@router.post(
    "/api/v1/uat/p1/cases",
    dependencies=[Depends(_require_portal_operator), Depends(_require_portal_access)],
)
def create_p1_uat_portal_case(
    body: P1UatPortalCaseCreate,
    db: Session = Depends(get_db),
):
    return _run_portal_action(
        lambda: p1_uat_portal_service.create_pending_case(
            db,
            buyer_alias=body.buyer_alias,
            product_name=body.product_name,
            quantity=body.quantity,
            requested_for=body.requested_for,
            special_requirement=body.special_requirement,
        )
    )


@router.post(
    "/api/v1/uat/p1/cases/{case_ref}/review",
    dependencies=[Depends(_require_portal_operator), Depends(_require_portal_access)],
)
def review_p1_uat_portal_case(case_ref: str, db: Session = Depends(get_db)):
    return _run_portal_action(
        lambda: p1_uat_portal_service.confirm_pending_review(db, case_ref=case_ref)
    )


@router.delete(
    "/api/v1/uat/p1",
    dependencies=[Depends(_require_portal_operator), Depends(_require_portal_access)],
)
def cleanup_p1_uat_portal(db: Session = Depends(get_db)):
    return _run_portal_action(lambda: p1_uat_portal_service.cleanup_portal(db))


_PORTAL_HTML = """<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>青泉谷 P1 staging UAT Portal</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; background: #f4f6f3; color: #16231b; }
    body { margin: 0; padding: 24px; }
    main { max-width: 820px; margin: 0 auto; }
    header, section { background: #fff; border: 1px solid #d9e2dc; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
    h1, h2 { margin-top: 0; }
    .marker { font-weight: 800; color: #9d1c1c; letter-spacing: .04em; }
    .boundary { background: #fff1f1; border-left: 5px solid #b42318; padding: 12px; font-weight: 700; }
    label { display: grid; gap: 6px; margin: 12px 0; font-weight: 650; }
    input, textarea, button { font: inherit; }
    input, textarea { padding: 10px; border: 1px solid #aebbb3; border-radius: 8px; }
    textarea { min-height: 84px; resize: vertical; }
    button { border: 0; border-radius: 8px; padding: 10px 14px; background: #176b45; color: white; cursor: pointer; margin: 4px 8px 4px 0; }
    button.danger { background: #a02b24; }
    button.secondary { background: #40534a; }
    pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #102018; color: #daf4e4; padding: 14px; border-radius: 8px; min-height: 52px; }
    .case { border-top: 1px solid #d9e2dc; padding: 12px 0; }
    small { color: #526158; }
  </style>
</head>
<body>
<main>
  <header>
    <div class="marker">STAGING SYNTHETIC ONLY</div>
    <h1>青泉谷 P1 UAT Portal</h1>
    <p class="boundary">不付款／不扣庫／不出貨／不開票</p>
    <p>本頁只建立 OrderAI synthetic event ledger 與加密的 <code>needs_human_review</code> 草稿；不連線 LINE、不送 ERP。</p>
  </header>

  <section>
    <h2>存取</h2>
    <label>Staging UAT Access Code
      <input id="accessCode" type="password" autocomplete="off" spellcheck="false">
    </label>
    <small>Access code 只保留於本頁目前的 JavaScript runtime，不使用 local storage。</small><br>
    <button id="statusButton" class="secondary" type="button">重新讀取安全狀態</button>
  </section>

  <section>
    <h2>建立合成訂單草稿</h2>
    <form id="caseForm">
      <label>訂購人代稱<input name="buyerAlias" required maxlength="120"></label>
      <label>商品<input name="productName" required maxlength="255"></label>
      <label>數量<input name="quantity" required type="number" min="1" max="99" value="1"></label>
      <label>需求時間<input name="requestedFor" required maxlength="120" placeholder="例如 2030-01-15T02:00:00+00:00"></label>
      <label>特殊要求<textarea name="specialRequirement" required maxlength="1000">無</textarea></label>
      <button type="submit">建立 pending 草稿</button>
    </form>
  </section>

  <section>
    <h2>安全狀態與人工覆核</h2>
    <div id="cases"></div>
    <button id="cleanupButton" class="danger" type="button">清理 synthetic 動態資料</button>
    <pre id="output">尚未執行。</pre>
  </section>
</main>
<script>
(() => {
  let accessCode = "";
  const codeInput = document.getElementById("accessCode");
  const output = document.getElementById("output");
  const cases = document.getElementById("cases");
  codeInput.addEventListener("input", () => { accessCode = codeInput.value; });

  async function api(path, options = {}) {
    const headers = { ...(options.headers || {}), "X-P1-UAT-Access-Code": accessCode };
    if (options.body) headers["Content-Type"] = "application/json";
    const response = await fetch(path, { ...options, headers, cache: "no-store" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload?.error?.message || `HTTP ${response.status}`);
    return payload.data;
  }

  function show(value) { output.textContent = JSON.stringify(value, null, 2); }
  function showError(error) { output.textContent = `操作失敗：${error.message}`; }

  function renderCases(data) {
    cases.replaceChildren();
    for (const row of data.cases || []) {
      const box = document.createElement("div");
      box.className = "case";
      const text = document.createElement("span");
      text.textContent = `${row.caseRef} — ${row.state} — version ${row.stateVersion}`;
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = row.reviewedPendingOnly ? "已人工查看（仍 pending）" : "人工確認並維持 pending";
      button.disabled = row.reviewedPendingOnly;
      button.addEventListener("click", async () => {
        try {
          show(await api(`/api/v1/uat/p1/cases/${encodeURIComponent(row.caseRef)}/review`, { method: "POST" }));
          await loadStatus();
        } catch (error) { showError(error); }
      });
      box.append(text, document.createElement("br"), button);
      cases.append(box);
    }
  }

  async function loadStatus() {
    try {
      const data = await api("/api/v1/uat/p1/status");
      renderCases(data);
      show(data);
    } catch (error) { showError(error); }
  }

  document.getElementById("statusButton").addEventListener("click", loadStatus);
  document.getElementById("caseForm").addEventListener("submit", async event => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const body = Object.fromEntries(form.entries());
    body.quantity = Number(body.quantity);
    try {
      show(await api("/api/v1/uat/p1/cases", { method: "POST", body: JSON.stringify(body) }));
      formElement.reset();
      await loadStatus();
    } catch (error) { showError(error); }
  });
  document.getElementById("cleanupButton").addEventListener("click", async () => {
    if (!confirm("只清理固定 synthetic store 的 UAT 動態資料，確定繼續？")) return;
    try {
      show(await api("/api/v1/uat/p1", { method: "DELETE" }));
      await loadStatus();
    } catch (error) { showError(error); }
  });
})();
</script>
</body>
</html>
"""
