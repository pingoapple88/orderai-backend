"""Local adapter for normalized OrderAI DEMO_MOCK screen view models."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


SUPPORTED_LOCALES = frozenset({"zh-Hant-TW", "en-US", "th-TH", "ja-JP", "id-ID"})
DEFAULT_LOCALE = "zh-Hant-TW"
SCREEN_IDS = frozenset({"orderai.parse_result", "orderai.risk_review", "orderai.queue"})
_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_PATH = _REPOSITORY_ROOT / "src" / "ui" / "fixtures" / "orderai" / "orderai_screen_scenarios.json"
_LOCALE_DIRECTORY = _REPOSITORY_ROOT / "src" / "ui" / "locales" / "orderai"
_SELF_SERVICE_FIXTURE_PATH = _REPOSITORY_ROOT / "src" / "ui" / "fixtures" / "orderai" / "orderai_self_service_projection.json"
_SELF_SERVICE_LOCALE_DIRECTORY = _LOCALE_DIRECTORY / "self_service"


class OrderAIDemoAdapter:
    """Reads versioned local fixture data without provider, queue, or database access."""

    def __init__(self, fixture_path: Path = _FIXTURE_PATH) -> None:
        self._fixture_path = fixture_path

    def normalize_locale(self, requested_locale: str | None) -> str:
        return requested_locale if requested_locale in SUPPORTED_LOCALES else DEFAULT_LOCALE

    def load_labels(self, requested_locale: str | None) -> dict[str, str]:
        locale = self.normalize_locale(requested_locale)
        return json.loads((_LOCALE_DIRECTORY / f"{locale}.json").read_text(encoding="utf-8"))

    def screen_models(self, scenario_id: str, requested_locale: str | None = None) -> list[dict[str, Any]]:
        fixture = json.loads(self._fixture_path.read_text(encoding="utf-8"))
        locale = self.normalize_locale(requested_locale)
        for scenario in fixture["scenarios"]:
            if scenario["scenario_id"] == scenario_id:
                models = deepcopy(scenario["view_models"])
                for model in models:
                    model["locale"] = locale
                return models
        raise KeyError(f"Unknown synthetic scenario: {scenario_id}")

    def self_service_model(self, requested_locale: str | None = None) -> dict[str, Any]:
        """Returns one safe synthetic self-service projection without billing or tenant authority."""
        model = json.loads(_SELF_SERVICE_FIXTURE_PATH.read_text(encoding="utf-8"))
        model["locale"] = self.normalize_locale(requested_locale)
        return deepcopy(model)

    def load_self_service_labels(self, requested_locale: str | None = None) -> dict[str, str]:
        locale = self.normalize_locale(requested_locale)
        return json.loads((_SELF_SERVICE_LOCALE_DIRECTORY / f"{locale}.json").read_text(encoding="utf-8"))
