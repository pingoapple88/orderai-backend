"""青泉谷 P1 的跨模組 localhost 合成驗收。

此測試在獨立 Python 程序啟動暫存 SQLite ERP，避免 OrderAI、ERP 同名 ``app``
套件衝突。所有身分、密鑰、客戶、商品與庫存皆為測試合成值；測試結束會停止
ERP 程序並刪除暫存資料庫。必須明確指定 ``P1_ERP_SOURCE_DIR`` 才執行。
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.interfaces.erp_ingest import IErpIngestProvider
from app.models import AuditLog, Customer, ErpDeliveryOutbox, IntakeConversation, Order, Product
from app.providers.erp_http import CloudDingErpIngestProvider
from app.services import p1_delivery_service
from tests.test_p1_delivery_service import _make_deliverable_case, _principal


_ERP_INGRESS_SECRET = "p1-isolated-acceptance-hmac-only"

_ERP_RUNNER = r'''
from pathlib import Path
import os

import uvicorn
from sqlalchemy import func

from app.core.database import Base, SessionLocal
import app.models  # noqa: F401 -- register all ORM models before create_all
from app.main import app
from app.models import (
    Company, Customer, InventoryLevel, Order, P1ServiceIngressReceipt,
    PendingConfirmationOrder, PendingCustomer, Product, SalesLocation, User, UserSalesLocationAccess, Warehouse,
)


Base.metadata.create_all(bind=SessionLocal.kw["bind"])
db = SessionLocal()
try:
    db.add_all([
        Company(id=1, code="QINGQUAN", name="青泉谷隔離驗收租戶"),
        User(
            id=901, company_id=1, username="p1_uat_admin",
            email="p1-uat-admin@isolated.invalid", password_hash="not-used",
            role="admin", is_active=True,
        ),
        User(
            id=903, company_id=1, username="p1_orderai_service",
            email="p1-orderai@isolated.invalid", password_hash="not-used",
            role="service", is_active=True,
        ),
        Product(id=101, company_id=1, sku="QG-EGG", name="青泉谷合成雞蛋", sale_price=120),
        Warehouse(id=11, company_id=1, code="QG-WH", name="合成履約倉", is_active=True, is_default=True),
        SalesLocation(
            id=91, company_id=1, warehouse_id=11, code="QG-MARKET",
            name="合成取貨據點", is_active=True,
        ),
        UserSalesLocationAccess(
            company_id=1, user_id=903, sales_location_id=91,
            is_active=True, granted_by=901,
        ),
        InventoryLevel(company_id=1, product_id=101, warehouse_id=11, on_hand=10, reserved=0),
    ])
    db.commit()
finally:
    db.close()


@app.get("/__p1_isolated_acceptance__/counts")
def isolated_counts():
    db = SessionLocal()
    try:
        pending_customer = db.query(PendingCustomer).filter_by(company_id=1).one_or_none()
        pending_order = db.query(PendingConfirmationOrder).filter_by(company_id=1).one_or_none()
        inventory = db.query(InventoryLevel).filter_by(
            company_id=1, product_id=101, warehouse_id=11,
        ).one()
        return {
            "ingress_receipts": db.query(P1ServiceIngressReceipt).filter_by(company_id=1).count(),
            "distinct_nonce_hmacs": db.query(
                func.count(func.distinct(P1ServiceIngressReceipt.nonce_hmac))
            ).filter_by(company_id=1).scalar(),
            "pending_customers": db.query(PendingCustomer).filter_by(company_id=1).count(),
            "pending_orders": db.query(PendingConfirmationOrder).filter_by(company_id=1).count(),
            "formal_customers": db.query(Customer).filter_by(company_id=1).count(),
            "formal_orders": db.query(Order).filter_by(company_id=1).count(),
            "inventory_reserved": inventory.reserved,
            "pending_customer_ciphertext_present": bool(
                pending_customer and pending_customer.display_name_encrypted
            ),
            "pending_customer_formal_customer_id": (
                pending_customer.formal_customer_id if pending_customer else None
            ),
            "pending_order_customer_linked": bool(
                pending_customer and pending_order
                and pending_order.pending_customer_id == pending_customer.id
            ),
            "pending_order_formal_order_id": (
                pending_order.formal_order_id if pending_order else None
            ),
        }
    finally:
        db.close()


Path(os.environ["P1_READY_FILE"]).write_text("ready", encoding="utf-8")
uvicorn.run(app, host="127.0.0.1", port=int(os.environ["P1_PORT"]), log_level="warning", access_log=False)
'''


def _erp_source_dir() -> Path:
    configured = os.environ.get("P1_ERP_SOURCE_DIR")
    if not configured:
        pytest.skip("P1_ERP_SOURCE_DIR 未設定；略過跨儲存庫 localhost 合成驗收")
    source_dir = Path(configured).resolve()
    if not (source_dir / "app" / "main.py").is_file():
        pytest.skip("P1_ERP_SOURCE_DIR 並非可用的 ERP 原始碼目錄")
    return source_dir


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start_isolated_erp(tmp_path: Path, erp_source_dir: Path):
    port = _free_local_port()
    runner = tmp_path / "erp_isolated_runner.py"
    ready_file = tmp_path / "erp_ready"
    db_path = tmp_path / "erp_isolated.sqlite3"
    runner.write_text(textwrap.dedent(_ERP_RUNNER), encoding="utf-8")
    environment = dict(os.environ)
    environment.update({
        "DATABASE_URL": f"sqlite:///{db_path}",
        "PII_ENC_KEY": Fernet.generate_key().decode("utf-8"),
        "PII_HMAC_KEY": "p1-isolated-acceptance-pii-hmac",
        "P1_ORDERAI_INGRESS_HMAC_SECRET": _ERP_INGRESS_SECRET,
        "P1_ORDERAI_SERVICE_USER_ID": "903",
        "P1_ORDERAI_SERVICE_ID": "orderai_p1",
        "P1_READY_FILE": str(ready_file),
        "P1_PORT": str(port),
        # 避免 OrderAI pytest 的 PYTHONPATH 汙染 ERP 子程序同名 app 套件。
        "PYTHONPATH": str(erp_source_dir),
    })
    process = subprocess.Popen(
        [sys.executable, str(runner)],
        cwd=erp_source_dir,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        if ready_file.exists():
            try:
                if httpx.get(f"{base_url}/health", timeout=0.3).status_code == 200:
                    return process, base_url
            except httpx.HTTPError:
                pass
        time.sleep(0.05)
    process.terminate()
    process.wait(timeout=3)
    raise AssertionError("暫存 ERP localhost 驗收服務未能就緒")


def _stop_isolated_erp(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def test_orderai_to_erp_pending_boundary_over_actual_localhost_hmac(db_session, monkeypatch, tmp_path):
    """人工覆核後只建立 ERP 待確認資料；不建正式客戶／訂單且不預留庫存。"""
    erp_source_dir = _erp_source_dir()
    process, base_url = _start_isolated_erp(tmp_path, erp_source_dir)
    try:
        store, case = _make_deliverable_case(db_session, monkeypatch)
        principal = _principal(db_session, store.id)
        monkeypatch.setattr(p1_delivery_service.settings, "p1_isolated_delivery_enabled", True)
        monkeypatch.setattr(p1_delivery_service.settings, "p1_erp_base_url", base_url)
        monkeypatch.setattr(
            p1_delivery_service.settings,
            "p1_erp_isolated_allowed_hosts",
            "localhost,127.0.0.1,::1",
        )
        p1_delivery_service.review_case(
            db_session, principal, store.id, case.id, customer_confirmed=True,
            note="合成買方已文字確認五項欄位",
        )
        provider: IErpIngestProvider = CloudDingErpIngestProvider(
            base_url=base_url,
            service_id="orderai_p1",
            ingress_hmac_secret=_ERP_INGRESS_SECRET,
            timeout_seconds=3,
        )
        delivered = asyncio.run(
            p1_delivery_service.dispatch_outbox(
                db_session, principal, store.id, case.id, provider=provider,
            )
        )
        assert delivered.status == "delivered" and delivered.attempt_count == 1
        assert db_session.get(IntakeConversation, case.id).state == "closed"
        assert db_session.execute(select(Order)).scalars().all() == []
        assert db_session.execute(select(Customer)).scalars().all() == []
        local_audit = json.dumps(
            [row.new_value for row in db_session.execute(select(AuditLog)).scalars()],
            ensure_ascii=False,
        )
        assert "0900000000" not in local_audit and "友善雞蛋 2 盒" not in local_audit

        counts = httpx.get(f"{base_url}/__p1_isolated_acceptance__/counts", timeout=3).json()
        assert counts == {
            "ingress_receipts": 2,
            "distinct_nonce_hmacs": 2,
            "pending_customers": 1,
            "pending_orders": 1,
            "formal_customers": 0,
            "formal_orders": 0,
            "inventory_reserved": 0,
            "pending_customer_ciphertext_present": True,
            "pending_customer_formal_customer_id": None,
            "pending_order_customer_linked": True,
            "pending_order_formal_order_id": None,
        }

        with pytest.raises(p1_delivery_service.P1StateConflict):
            asyncio.run(
                p1_delivery_service.dispatch_outbox(
                    db_session, principal, store.id, case.id, provider=provider,
                )
            )
        assert httpx.get(f"{base_url}/__p1_isolated_acceptance__/counts", timeout=3).json() == counts
    finally:
        _stop_isolated_erp(process)
