"""Focused tests for the local, accessible OrderAI screen renderer."""

from src.ui.screens.orderai import OrderAIScreenRenderer
from pathlib import Path


def test_renderer_outputs_three_accessible_demo_screens_for_approved_path():
    html = OrderAIScreenRenderer().render_scenario("parse_success", "zh-Hant-TW")

    assert html.count('data-screen-id="orderai.') == 3
    assert "Demo／合成資料" in html
    assert "正式服務：未連接" in html
    assert "data-action-id=\"orderai.submit_synthetic_input\"" in html
    assert 'data-result-state="loading"' in html
    assert "已通過" in html
    assert 'role="status"' in html
    assert 'data-target-screen="orderai-risk_review"' in html
    assert 'data-action-label="解析合成輸入"' in html


def test_renderer_keeps_manual_retry_confirmation_and_redacted_failure_paths():
    html = OrderAIScreenRenderer().render_scenario("dead_letter_manual_retry", "en-US")

    assert 'data-action-id="orderai.manual_retry"' in html
    assert 'data-requires-confirmation="true"' in html
    assert 'data-result-state="processing"' in html
    assert 'aria-live="polite"' in html
    assert "http://" not in html and "https://" not in html
    assert "company_id" not in html and "reply_token" not in html


def test_renderer_uses_adapter_locale_fallback_and_no_template_hardcoded_title():
    renderer = OrderAIScreenRenderer()
    fallback_html = renderer.render_scenario("empty_state", "zh-TW")
    japanese_html = renderer.render_scenario("empty_state", "ja-JP")

    assert "尚未選擇合成輸入。" in fallback_html
    assert "合成入力が選択されていません。" in japanese_html
    assert "Unknown synthetic scenario" not in fallback_html


def test_local_interaction_script_has_feedback_and_confirm_dialog_without_external_runtime():
    script = (Path(__file__).resolve().parents[3] / "src" / "ui" / "screens" / "orderai" / "orderai_screen_interactions.js").read_text(encoding="utf-8")

    assert "showFeedback" in script
    assert "showConfirmDialog" in script
    assert "dialog.showModal()" in script
    assert "http://" not in script and "https://" not in script
    assert "onclick=" not in script
