"""IAuthProvider（律一/集團守則：外部認證服務必須抽象）。"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AuthProfile:
    """各 provider 統一回傳的使用者輪廓。"""
    provider: str
    external_id: str          # 例如 LINE userId 字串
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
    email: Optional[str] = None


class IAuthProvider(ABC):
    """認證 Adapter 介面。具體實作見 app/providers/。"""

    @abstractmethod
    def get_authorize_url(self, state: str) -> str:
        """產生 OAuth 授權導向 URL。"""

    @abstractmethod
    async def exchange_code(self, code: str) -> AuthProfile:
        """用授權碼換 token 並取得使用者輪廓。"""
