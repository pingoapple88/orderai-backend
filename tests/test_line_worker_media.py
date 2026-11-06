"""WO-L3-003 對話層③：照片／語音／口語收單（真 PostgreSQL + mock LINE content／STT／LLM）。"""
from __future__ import annotations

import asyncio
import base64
import json

import httpx
import pytest
from sqlalchemy import func, select

from app.core.interfaces.llm_provider import ExtractedItem, ExtractionResult
from app.core.interfaces.message_content_provider import MessageContent, MessageContentError
from app.core.interfaces.speech_to_text_provider import SpeechToTextError, Transcription
from app.models import AuditLog, Order, OrderItem, Plan, Product, Store, User
from app.providers import http_chat_llm, http_stt, line_content
from app.workers import line_worker

PNG = b"\x89PNG\r\n\x1a\nfake-image-bytes"
M4A = b"fake-m4a-bytes"


class _FakeLLM:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc
        self.calls = []

    async def extract_order(self, text=None, image_url=None, industry_type="ecom"):
        self.calls.append({"text": text, "image_url": image_url, "industry_type": industry_type})
        if self.exc:
            raise self.exc
        return self.result


class _FakeNotif:
    def __init__(self):
        self.sent = []

    async def send_message(self, to, text, reply_token=None):
        self.sent.append({"to": to, "text": text, "reply_token": reply_token})


class _FakeContent:
    def __init__(self, data=PNG, content_type="image/png", exc=None):
        self.data, self.content_type, self.exc = data, content_type, exc
        self.calls = []

    async def get_message_content(self, message_id):
        self.calls.append(message_id)
        if self.exc:
            raise self.exc
        return MessageContent(data=self.data, content_type=self.content_type)


class _FakeSTT:
    def __init__(self, text="我要兩盒蛋", confidence=0.92, exc=None):
        self.text, self.confidence, self.exc = text, confidence, exc
        self.calls = []

    async def transcribe(self, audio, *, content_type="audio/m4a", language="zh"):
        self.calls.append({"audio": audio, "content_type": content_type, "language": language})
        if self.exc:
            raise self.exc
        return Transcription(text=self.text, confidence=self.confidence, provider_name="fake")


def _install(monkeypatch, *, llm, notif, store_id, content=None, stt=None):
    monkeypatch.setattr("app.providers.get_llm_provider", lambda: llm)
    monkeypatch.setattr("app.providers.get_notification_provider", lambda: notif)
    monkeypatch.setattr("app.providers.get_message_content_provider", lambda: content or _FakeContent())
    monkeypatch.setattr("app.providers.get_speech_to_text_provider", lambda: stt or _FakeSTT())
    monkeypatch.setattr(line_worker.settings, "default_store_id", store_id)
    monkeypatch.setattr(line_worker.settings, "p1_intake_enabled", False)
    monkeypatch.setattr(line_worker.settings, "reply_llm_enabled", False)


def _seed(db):
    plan = Plan(name="lite", channel="direct", monthly_price=0)
    db.add(plan)
    db.flush()
    store = Store(name="日日好蛋", industry_type="ecom", market="tw")
    db.add(store)
    db.flush()
    owner = User(line_id="Uowner", name="老闆", role="owner", store_id=store.id, plan_id=plan.id)
    egg = Product(store_id=store.id, name="蛋", aliases=["雞蛋"], unit="盒", price_cents=12000)
    apple = Product(store_id=store.id, name="蘋果", aliases=[], unit="顆", price_cents=4500)
    db.add_all([owner, egg, apple])
    db.commit()
    return store, owner


def _result(name="蛋", qty=2, conf=0.93, evidence="兩盒蛋", llm_price=1):
    # llm_price：模擬模型夾帶價格；系統必須忽略、只用型錄。
    return ExtractionResult(
        items=[ExtractedItem(product_name=name, quantity=qty, unit="盒", unit_price=llm_price,
                             evidence=evidence, confidence_score=conf)],
        confidence_score=conf, industry_type="ecom", provider_name="fake",
        raw={"items": [{"product_name": name, "quantity": qty, "unit_price": llm_price}]},
    )


def _payload(msg, event_id="evt-m1"):
    return {"destination": "Ubot", "events": [{
        "type": "message", "webhookEventId": event_id, "replyToken": "rt-" + event_id,
        "source": {"type": "user", "userId": "Ubuyer01"}, "message": msg,
    }]}


def _run(payload, db):
    asyncio.run(line_worker.process_webhook_event(payload, db=db))


def _orders(db):
    return db.execute(select(Order)).scalars().all()


def _decisions(db):
    return db.execute(
        select(AuditLog).where(AuditLog.action == "ai.order.decision").order_by(AuditLog.id)
    ).scalars().all()


# ── 圖片 ────────────────────────────────────────────────────────────────────
def test_image_message_creates_order_with_catalog_price(db_session, monkeypatch):
    store, owner = _seed(db_session)
    llm, notif, content = _FakeLLM(result=_result(llm_price=1)), _FakeNotif(), _FakeContent()
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id, content=content)
    _run(_payload({"type": "image", "id": "5551234"}), db_session)

    assert content.calls == ["5551234"]
    assert len(llm.calls) == 1
    expected_url = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
    assert llm.calls[0]["image_url"] == expected_url
    orders = _orders(db_session)
    assert len(orders) == 1
    assert orders[0].total_cents == 24000          # 12000 × 2，型錄價；LLM 回的 1 被忽略
    item = db_session.execute(select(OrderItem)).scalars().one()
    assert item.unit_price_cents == 12000 and item.quantity == 2
    assert notif.sent and "總計 $240" in notif.sent[0]["text"]


def test_image_low_confidence_needs_review_no_order(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result(conf=0.4)), _FakeNotif()
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id)
    _run(_payload({"type": "image", "id": "5551235"}), db_session)

    assert _orders(db_session) == []
    dec = _decisions(db_session)[-1]
    assert dec.new_value["status"] == "needs_review"
    assert "confidence_below_threshold" in dec.new_value["reason_codes"]
    assert notif.sent and "確認" in notif.sent[0]["text"]


def test_image_fetch_failure_fail_closed_without_llm(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result()), _FakeNotif()
    content = _FakeContent(exc=MessageContentError("media_fetch_failed"))
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id, content=content)
    _run(_payload({"type": "image", "id": "5551236"}), db_session)

    assert _orders(db_session) == [] and llm.calls == []
    assert _decisions(db_session)[-1].new_value["reason_codes"] == ["media_fetch_failed"]
    assert notif.sent and "media_fetch_failed" not in notif.sent[0]["text"]


def test_image_wrong_content_type_needs_review(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result()), _FakeNotif()
    content = _FakeContent(content_type="text/html")
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id, content=content)
    _run(_payload({"type": "image", "id": "5551237"}), db_session)
    assert _orders(db_session) == [] and llm.calls == []
    assert _decisions(db_session)[-1].new_value["reason_codes"] == ["media_type_mismatch"]


def test_image_intake_disabled_skips(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif, content = _FakeLLM(result=_result()), _FakeNotif(), _FakeContent()
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id, content=content)
    monkeypatch.setattr(line_worker.settings, "line_image_intake_enabled", False)
    _run(_payload({"type": "image", "id": "5551238"}), db_session)
    assert content.calls == [] and llm.calls == [] and notif.sent == [] and _orders(db_session) == []


# ── 語音 ────────────────────────────────────────────────────────────────────
def test_audio_message_transcribed_then_order(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result(llm_price=99999)), _FakeNotif()
    content = _FakeContent(data=M4A, content_type="audio/m4a")
    stt = _FakeSTT(text="我要兩盒蛋", confidence=0.9)
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id, content=content, stt=stt)
    _run(_payload({"type": "audio", "id": "7770001", "duration": 2000}), db_session)

    assert stt.calls and stt.calls[0]["audio"] == M4A and stt.calls[0]["content_type"] == "audio/m4a"
    assert llm.calls == [{"text": "我要兩盒蛋", "image_url": None, "industry_type": "ecom"}]
    orders = _orders(db_session)
    assert len(orders) == 1 and orders[0].total_cents == 24000   # LLM 價 99999 被忽略


@pytest.mark.parametrize("stt,reason", [
    (_FakeSTT(confidence=0.3), "stt_confidence_below_threshold"),
    (_FakeSTT(confidence=None), "stt_confidence_unavailable"),
    (_FakeSTT(text="  "), "stt_empty_transcript"),
    (_FakeSTT(exc=SpeechToTextError("stt_not_configured")), "stt_not_configured"),
])
def test_audio_uncertain_needs_review_no_llm_no_order(db_session, monkeypatch, stt, reason):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result()), _FakeNotif()
    content = _FakeContent(data=M4A, content_type="audio/m4a")
    stt.calls = []
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id, content=content, stt=stt)
    _run(_payload({"type": "audio", "id": "7770002"}), db_session)

    assert _orders(db_session) == [] and llm.calls == []
    dec = _decisions(db_session)[-1]
    assert dec.new_value["status"] == "needs_review" and dec.new_value["reason_codes"] == [reason]
    assert notif.sent and "確認" in notif.sent[0]["text"] and reason not in notif.sent[0]["text"]


def test_default_stt_provider_is_disabled_fail_closed(monkeypatch):
    from app import providers
    monkeypatch.setattr(providers.settings, "stt_provider", "")
    p = providers.get_speech_to_text_provider()
    assert isinstance(p, http_stt.DisabledSpeechToTextProvider)
    with pytest.raises(SpeechToTextError) as ei:
        asyncio.run(p.transcribe(M4A))
    assert ei.value.reason_code == "stt_not_configured"


# ── 口語 ────────────────────────────────────────────────────────────────────
def test_colloquial_text_creates_order_with_catalog_price(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result(llm_price=5)), _FakeNotif()
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id)
    _run(_payload({"type": "text", "id": "1", "text": "老闆我要兩盒蛋"}), db_session)
    orders = _orders(db_session)
    assert len(orders) == 1 and orders[0].total_cents == 24000
    assert llm.calls[0]["text"] == "老闆我要兩盒蛋" and llm.calls[0]["image_url"] is None


def test_colloquial_ambiguous_quantity_needs_review(db_session, monkeypatch):
    store, _ = _seed(db_session)
    llm, notif = _FakeLLM(result=_result(qty=None, evidence="蛋給我來一些")), _FakeNotif()
    _install(monkeypatch, llm=llm, notif=notif, store_id=store.id)
    _run(_payload({"type": "text", "id": "2", "text": "蛋給我來一些"}), db_session)
    assert _orders(db_session) == []
    assert "invalid_quantity" in _decisions(db_session)[-1].new_value["reason_codes"]


def _mock_transport(capture, content):
    def handler(request: httpx.Request) -> httpx.Response:
        capture.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(content)}}]})
    return httpx.MockTransport(handler)


def test_http_provider_colloquial_prompt_and_ignores_llm_price(monkeypatch):
    capture = []
    llm_out = {"items": [{"product_name": "蛋", "quantity": 2, "unit": "盒", "unit_price": 1,
                          "evidence": "兩盒蛋", "field_confidence": 0.9}], "confidence_score": 0.9}
    real_client = httpx.AsyncClient
    monkeypatch.setattr(http_chat_llm.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=_mock_transport(capture, llm_out)))
    p = http_chat_llm.OpenAICompatibleLLMProvider(api_key="k", api_base="http://llm.test/v1", model="m")
    res = asyncio.run(p.extract_order(text="我要兩盒蛋"))
    system = capture[0]["messages"][0]["content"]
    assert "我要兩盒蛋" in system and "兩/二=2" in system and "價格" in system
    assert res.items[0].quantity == 2 and res.items[0].unit == "盒"
    assert res.items[0].unit_price is None           # 模型價格不進入結構化結果


def test_anthropic_image_data_url_becomes_base64_source():
    src = http_chat_llm._anthropic_image_source("data:image/png;base64,QUJD")
    assert src == {"type": "base64", "media_type": "image/png", "data": "QUJD"}
    assert http_chat_llm._anthropic_image_source("https://x/y.png") == {"type": "url", "url": "https://x/y.png"}


# ── LINE content adapter（mock LINE content API，不連正式）──────────────────
def _patch_line_client(monkeypatch, handler):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(line_content.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler)))


def test_line_content_adapter_fetches_with_token(monkeypatch):
    seen = {}

    def handler(request):
        seen["url"], seen["auth"] = str(request.url), request.headers.get("authorization")
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    _patch_line_client(monkeypatch, handler)
    p = line_content.LineMessageContentProvider(access_token="tok-test", max_bytes=1000, timeout_seconds=1)
    got = asyncio.run(p.get_message_content("5551234"))
    assert got.data == PNG and got.content_type == "image/png"
    assert seen["url"] == "https://api-data.line.me/v2/bot/message/5551234/content"
    assert seen["auth"] == "Bearer tok-test"


@pytest.mark.parametrize("token,mid,status,body,reason", [
    ("", "1", 200, PNG, "media_token_not_configured"),
    ("t", "../x", 200, PNG, "media_id_invalid"),
    ("t", "1", 404, b"", "media_fetch_failed"),
    ("t", "1", 200, b"x" * 2000, "media_too_large"),
    ("t", "1", 200, b"", "media_empty"),
])
def test_line_content_adapter_fail_closed(monkeypatch, token, mid, status, body, reason):
    _patch_line_client(monkeypatch, lambda request: httpx.Response(status, content=body))
    p = line_content.LineMessageContentProvider(access_token=token, max_bytes=1000, timeout_seconds=1)
    with pytest.raises(MessageContentError) as ei:
        asyncio.run(p.get_message_content(mid))
    assert ei.value.reason_code == reason


def test_stt_adapter_confidence_from_segments(monkeypatch):
    def handler(request):
        assert request.url.path == "/v1/audio/transcriptions"
        return httpx.Response(200, json={"text": "我要兩盒蛋",
                                         "segments": [{"avg_logprob": -0.1}, {"avg_logprob": -0.2}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(http_stt.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(handler)))
    p = http_stt.OpenAICompatibleSpeechToTextProvider(api_base="http://stt.test/v1", model="m")
    tr = asyncio.run(p.transcribe(M4A))
    assert tr.text == "我要兩盒蛋" and 0.86 < tr.confidence < 0.87


def test_stt_adapter_no_segments_confidence_none(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(http_stt.httpx, "AsyncClient",
                        lambda **kw: real_client(transport=httpx.MockTransport(
                            lambda r: httpx.Response(200, json={"text": "hi"}))))
    p = http_stt.OpenAICompatibleSpeechToTextProvider(api_base="http://stt.test/v1", model="m")
    assert asyncio.run(p.transcribe(M4A)).confidence is None
