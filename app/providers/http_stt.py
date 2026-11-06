"""ISpeechToTextProvider 實作：OpenAI-compatible `/audio/transcriptions`（HTTP，不用廠商 SDK）。

信心：以 verbose_json segments 的 avg_logprob 換算 exp(平均)；無 segments → confidence=None，
由業務層 fail-closed（轉人工）。
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import httpx

from app.core.interfaces.speech_to_text_provider import ISpeechToTextProvider, SpeechToTextError, Transcription

_EXT = {
    "audio/m4a": "m4a", "audio/x-m4a": "m4a", "audio/mp4": "m4a", "audio/aac": "aac",
    "audio/mpeg": "mp3", "audio/wav": "wav", "audio/x-wav": "wav", "audio/ogg": "ogg", "audio/webm": "webm",
}


def _confidence_from_segments(segments: Any) -> Optional[float]:
    if not isinstance(segments, list) or not segments:
        return None
    logprobs: List[float] = []
    for seg in segments:
        if isinstance(seg, dict) and isinstance(seg.get("avg_logprob"), (int, float)):
            logprobs.append(float(seg["avg_logprob"]))
    if not logprobs:
        return None
    return max(0.0, min(1.0, math.exp(sum(logprobs) / len(logprobs))))


class DisabledSpeechToTextProvider(ISpeechToTextProvider):
    """STT_PROVIDER 未設定：一律拋錯 → 語音訊息轉人工，不猜。"""

    provider_name = "disabled"

    async def transcribe(self, audio: bytes, *, content_type: str = "audio/m4a", language: str = "zh") -> Transcription:
        raise SpeechToTextError("stt_not_configured")


class OpenAICompatibleSpeechToTextProvider(ISpeechToTextProvider):
    provider_name = "openai_compatible_stt"

    def __init__(self, *, api_key: str = "", api_base: str = "", model: str = "",
                 timeout_seconds: float = 30.0) -> None:
        self.api_key = api_key
        self.api_base = api_base
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def transcribe(self, audio: bytes, *, content_type: str = "audio/m4a", language: str = "zh") -> Transcription:
        if not self.api_base or not self.model:
            raise SpeechToTextError("stt_not_configured")
        if not audio:
            raise SpeechToTextError("stt_empty_audio")
        headers: Dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = "Bearer {}".format(self.api_key)
        ext = _EXT.get(content_type, "m4a")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.post(
                    "{}/audio/transcriptions".format(self.api_base.rstrip("/")),
                    headers=headers,
                    data={"model": self.model, "language": language, "response_format": "verbose_json",
                          "temperature": "0"},
                    files={"file": ("audio.{}".format(ext), audio, content_type)},
                )
                resp.raise_for_status()
                payload = resp.json()
        except (httpx.TimeoutException, TimeoutError) as exc:
            raise SpeechToTextError("stt_timeout") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise SpeechToTextError("stt_error") from exc
        if not isinstance(payload, dict):
            raise SpeechToTextError("stt_error")
        text = str(payload.get("text") or "").strip()
        return Transcription(
            text=text,
            confidence=_confidence_from_segments(payload.get("segments")),
            provider_name=self.provider_name,
        )
