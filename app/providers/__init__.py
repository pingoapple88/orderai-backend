"""Provider 工廠：依設定回傳對應 Adapter（集團守則：可替換）。"""
from app.core.config import get_settings
from app.core.interfaces.auth_provider import IAuthProvider
from app.core.interfaces.llm_provider import ILLMProvider
from app.core.interfaces.payment_provider import IPaymentProvider
from app.providers.line_auth import LineAuthProvider
from app.providers.openai_llm import OpenAILLMProvider
from app.providers.stallpay import StallPayProvider

settings = get_settings()


def get_auth_provider() -> IAuthProvider:
    return LineAuthProvider()


def get_llm_provider() -> ILLMProvider:
    match settings.llm_provider.lower():
        case _:
            return OpenAILLMProvider()


def get_payment_provider() -> IPaymentProvider:
    # OrderAI 不自處理金流，一律委派 StallPay
    return StallPayProvider()
