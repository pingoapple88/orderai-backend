"""ISpeechToTextProvider（集團守則：AI 服務可替換）：語音轉文字。

confidence 為 0–1；Provider 無法提供信心時回 None，由業務層 fail-closed 決定是否轉人工。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Transcription:
    text: str
    confidence: Optional[float] = None
    provider_name: str = ""


class SpeechToTextError(RuntimeError):
    def __init__(self, reason_code: str, message: str = "") -> None:
        super().__init__(message or reason_code)
        self.reason_code = reason_code


class ISpeechToTextProvider(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, *, content_type: str = "audio/m4a", language: str = "zh") -> Transcription:
        """將語音轉為文字；失敗一律拋 SpeechToTextError。"""
