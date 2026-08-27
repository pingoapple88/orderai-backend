from app.adapters.merchcore_module import SUPPORTED_LOCALES
from app.core.i18n import _MESSAGES, t


def test_i18n_message_table_uses_exactly_the_module_five_locale_contract():
    assert set(_MESSAGES) == set(SUPPORTED_LOCALES)
    for locale in SUPPORTED_LOCALES:
        assert t("order_not_found", locale)
        assert t("unauthorized", locale)


def test_unsupported_locale_falls_back_to_zh_hant_tw():
    assert t("order_not_found", "zh-TW") == t("order_not_found", "zh-Hant-TW")
