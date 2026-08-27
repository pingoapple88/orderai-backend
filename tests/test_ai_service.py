from app.services import ai_service


def test_order_prefilter_without_config_keeps_existing_default(monkeypatch):
    monkeypatch.setattr(ai_service, "get_setting", lambda _db, _key: None)
    assert ai_service.is_order_message(object(), "蘋果 2 顆") is True


def test_order_prefilter_with_invalid_regex_fails_closed(monkeypatch):
    monkeypatch.setattr(ai_service, "get_setting", lambda _db, _key: "[")
    assert ai_service.is_order_message(object(), "蘋果 2 顆") is False
