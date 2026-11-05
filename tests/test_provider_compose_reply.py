"""WO-L3-002：provider compose_reply(outcome, brand_voice) -> (opening, closing)。

補 WO-L3-001 的缺口——PR#39 的 reply_composer 以 getattr 呼叫 compose_reply，但無 provider
實作，暖話永遠走罐頭句。本 WO 在 provider 實作後，暖話才真正生效（數字仍由程式精算）。
"""
from __future__ import annotations

import asyncio

import pytest

from app.providers import http_chat_llm as hc
from app.providers.http_chat_llm import OpenAICompatibleLLMProvider
from app.providers.failover_llm import FailoverLLMProvider
from app.services import reply_composer as rc


class _Resp:
    def __init__(self, content: str) -> None:
        self._c = content

    def json(self):
        return {"choices": [{"message": {"content": self._c}}]}


def test_openai_compose_reply_returns_tuple(monkeypatch):
    async def fake_post(client, url, *, headers=None, payload, max_retries):
        # 確認送出的是暖話 system（不是訂單抽取），且溫度較高。
        assert payload["temperature"] == 0.7
        return _Resp('{"opening": "哈囉～歡迎光臨", "closing": "我們馬上為您準備"}')

    monkeypatch.setattr(hc, "_post_json", fake_post)
    p = OpenAICompatibleLLMProvider(api_key="k", api_base="http://x", model="m")
    opening, closing = asyncio.run(p.compose_reply(outcome="order_created", brand_voice="青泉谷小農"))
    assert opening == "哈囉～歡迎光臨"
    assert closing == "我們馬上為您準備"


def test_openai_compose_reply_bad_json_raises(monkeypatch):
    async def fake_post(client, url, *, headers=None, payload, max_retries):
        return _Resp("not-json")

    monkeypatch.setattr(hc, "_post_json", fake_post)
    p = OpenAICompatibleLLMProvider(api_key="k", api_base="http://x", model="m")
    with pytest.raises(Exception):
        asyncio.run(p.compose_reply(outcome="order_created", brand_voice=""))


def test_openai_compose_reply_empty_raises(monkeypatch):
    async def fake_post(client, url, *, headers=None, payload, max_retries):
        return _Resp('{"opening": "", "closing": ""}')

    monkeypatch.setattr(hc, "_post_json", fake_post)
    p = OpenAICompatibleLLMProvider(api_key="k", api_base="http://x", model="m")
    with pytest.raises(Exception):
        asyncio.run(p.compose_reply(outcome="order_created", brand_voice=""))


def test_failover_compose_reply_uses_fallback():
    class _Boom:
        async def compose_reply(self, outcome, brand_voice=""):
            raise RuntimeError("primary down")

    class _Ok:
        async def compose_reply(self, outcome, brand_voice=""):
            return ("備援開場", "備援結尾")

    fo = FailoverLLMProvider(_Boom(), _Ok())
    assert asyncio.run(fo.compose_reply(outcome="order_created", brand_voice="")) == ("備援開場", "備援結尾")


def test_warmth_fires_end_to_end_through_composer():
    """關鍵：provider 實作 compose_reply 後，PR#39 composer 真的用暖話包住事實區塊（數字仍程式算）。"""

    class _Warm:
        async def compose_reply(self, outcome, brand_voice=""):
            return ("歡迎光臨青泉谷", "我們馬上為您準備")

    items = [rc.ReplyItem(name="優質放牧雞蛋", qty=2, unit_price_cents=16500)]
    text = asyncio.run(
        rc.compose(rc.OUTCOME_ORDER_CREATED, items=items, total_cents=33000, llm=_Warm(), brand_voice="青泉谷")
    )
    assert text.startswith("歡迎光臨青泉谷")          # LLM 開場白
    assert text.endswith("我們馬上為您準備")           # LLM 結尾
    assert "總計 $330" in text                        # 事實區塊，數字由程式精算
    assert "優質放牧雞蛋" in text
