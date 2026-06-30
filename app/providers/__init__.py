"""Provider 工廠：依設定回傳對應 Adapter（集團守則：可替換）。"""
from app.core.config import get_settings
from app.core.interfaces.auth_provider import IAuthProvider
from app.core.interfaces.llm_provider import ILLMProvider
from app.providers.line_auth import LineAuthProvider
from app.providers.openai_llm import OpenAILLMProvider

settings = get_settings()


def get_auth_provider() -> IAuthProvider:
    # 目前僅 LINE；未來可依 provider 名稱切換
    return LineAuthProvider()


def get_llm_provider() -> ILLMProvider:
    match settings.llm_provider.lower():
        # case "claude": return ClaudeLLMProvider()
        # case "ollama": return OllamaLLMProvider()
        case _:
            return OpenAILLMProvider()
