"""Accessible, local-only HTML fragments for OrderAI DEMO_MOCK screen models."""

from __future__ import annotations

from html import escape
from typing import Any

from src.adapters.orderai_adapter import OrderAIDemoAdapter


class OrderAIScreenRenderer:
    """Renders versioned screen models without network, provider, queue, or database access."""

    def __init__(self, adapter: OrderAIDemoAdapter | None = None) -> None:
        self._adapter = adapter or OrderAIDemoAdapter()

    def render_scenario(self, scenario_id: str, requested_locale: str | None = None) -> str:
        labels = self._adapter.load_labels(requested_locale)
        models = self._adapter.screen_models(scenario_id, requested_locale)
        panels = "".join(self._render_model(model, labels) for model in models)
        return f'<main class="mc-orderai-screens" data-scenario="{escape(scenario_id)}">{panels}</main>'

    def render_self_service_entry(self, requested_locale: str | None = None) -> str:
        """Renders a local-only product entry projection for T1 to embed in the Demo shell."""
        model = self._adapter.self_service_model(requested_locale)
        labels = self._adapter.load_self_service_labels(requested_locale)
        channels = "".join(
            f'<li><strong>{self._label(labels, option["label_key"])}</strong><span>{self._label(labels, option["availability_key"])}</span></li>'
            for option in model["data"]["channels"]
        )
        quota = model["data"]["ai_quota"]
        billing = model["data"]["billing"]
        return (
            f'<section class="mc-orderai-panel mc-self-service-entry" id="orderai-self-service-entry" '
            f'data-screen-id="{escape(model["screen_id"])}" data-status="{escape(model["status"])}" '
            f'aria-labelledby="orderai-self-service-entry-title">'
            f'<p class="mc-demo-badge" aria-label="{self._label(labels, "orderai.self_service.badge_aria")}">'
            f'<span>{self._label(labels, "orderai.self_service.demo")}</span>'
            f'<span>{self._label(labels, "orderai.self_service.formal")}</span></p>'
            f'<header><p class="mc-screen-kicker">{escape(model["screen_id"])}</p>'
            f'<h2 id="orderai-self-service-entry-title">{self._label(labels, model["title_key"])}</h2>'
            f'<p>{self._label(labels, model["subtitle_key"])}</p>'
            f'<span class="mc-status-badge" role="status">{self._label(labels, model["status_key"])}</span></header>'
            f'<div class="mc-screen-data"><h3>{self._label(labels, "orderai.self_service.channels")}</h3><ul class="mc-item-list">{channels}</ul>'
            f'<dl class="mc-risk-data"><div><dt>{self._label(labels, "orderai.self_service.entitlement")}</dt>'
            f'<dd>{self._label(labels, model["data"]["entitlement"]["status_key"])}</dd></div>'
            f'<div><dt>{self._label(labels, "orderai.self_service.quota")}</dt><dd>{quota["sample_used"]}/{quota["sample_limit"]} '
            f'{self._label(labels, quota["unit_key"])}</dd></div>'
            f'<div><dt>{self._label(labels, "orderai.self_service.billing")}</dt><dd>{self._label(labels, billing["payment_status_key"])}</dd></div>'
            f'<div><dt>{self._label(labels, "orderai.self_service.invoice")}</dt><dd>{self._label(labels, billing["invoice_status_key"])}</dd></div>'
            f'<div><dt>{self._label(labels, "orderai.self_service.scope")}</dt><dd>{self._label(labels, model["data"]["scope_authority_key"])}</dd></div></dl></div>'
            f'<nav class="mc-screen-actions" aria-label="{self._label(labels, "orderai.self_service.actions_aria")}">'
            f'<button class="mc-action-button" type="button" data-action-id="orderai.start_synthetic_parse" '
            f'data-requires-confirmation="false" data-result-state="loading" '
            f'data-result-label="{self._label(labels, "orderai.self_service.loading")}" '
            f'data-action-label="{self._label(labels, "orderai.self_service.start_parse")}" '
            f'data-target-screen="orderai-parse_result">{self._label(labels, "orderai.self_service.start_parse")}</button></nav>'
            f'<p class="mc-action-feedback" role="status" aria-live="polite" hidden></p></section>'
        )

    def _render_model(self, model: dict[str, Any], labels: dict[str, str]) -> str:
        title = self._label(labels, model["title_key"])
        subtitle = self._label(labels, model.get("subtitle_key"))
        status = model["status"]
        status_label = self._label(labels, f"orderai.status.{status}")
        screen_id = escape(model["screen_id"])
        metadata = (
            f'<p class="mc-demo-badge" aria-label="{self._label(labels, "orderai.badge.aria")}">'
            f'<span>{self._label(labels, "orderai.badge.demo")}</span>'
            f'<span>{self._label(labels, "orderai.badge.mode")}: {escape(model["mode"])}</span>'
            f'<span>{self._label(labels, "orderai.badge.evidence")}: {escape(model["evidence_level"])}</span>'
            f'<span>{self._label(labels, "orderai.badge.formal")}</span></p>'
        )
        error = self._render_error(model.get("error"), labels)
        action_markup = self._render_actions(model.get("actions", []), labels)
        data_markup = self._render_data(model, labels)
        return (
            f'<section class="mc-orderai-panel mc-status-{escape(status)}" id="{screen_id.replace(".", "-")}" '
            f'data-screen-id="{screen_id}" data-status="{escape(status)}" aria-labelledby="{screen_id}-title">'
            f'{metadata}<header><p class="mc-screen-kicker">{screen_id}</p><h2 id="{screen_id}-title">{title}</h2>'
            f'<p>{subtitle}</p><span class="mc-status-badge" role="status">{status_label}</span></header>'
            f'{data_markup}{error}{action_markup}<p class="mc-action-feedback" role="status" aria-live="polite" hidden></p>'
            f'<footer><span>{self._label(labels, "orderai.audit_reference")}: {escape(model["audit_reference"])}</span>'
            f'<time datetime="{escape(model["updated_at"])}">{escape(model["updated_at"])}</time></footer></section>'
        )

    def _render_data(self, model: dict[str, Any], labels: dict[str, str]) -> str:
        data = model["data"]
        if model["screen_id"] == "orderai.parse_result":
            input_summary = data.get("input_summary")
            input_markup = ""
            if input_summary:
                input_markup = f'<p class="mc-input-summary"><strong>{self._label(labels, "orderai.parse.input_summary")}:</strong> {escape(input_summary)}</p>'
            items = "".join(
                f'<li><span>{escape(item["product_name"])}</span><span>{item["quantity"]} × {item["amount_minor"]} {escape(item["currency"])} · {escape(item["catalog_status"])} · {item["confidence"]}</span></li>'
                for item in data.get("items", [])
            )
            item_list = f'<ul class="mc-item-list">{items}</ul>' if items else f'<p class="mc-empty-copy">{self._label(labels, "orderai.empty.items")}</p>'
            return f'<div class="mc-screen-data">{input_markup}{item_list}</div>'
        if model["screen_id"] == "orderai.risk_review":
            approval_state = data.get("approval_state", "needs_review")
            decision = self._label(labels, f"orderai.decision.{approval_state}")
            reasons = ", ".join(escape(reason) for reason in data.get("reason_codes", [])) or self._label(labels, "orderai.empty.reasons")
            return (
                '<dl class="mc-risk-data">'
                f'<div><dt>{self._label(labels, "orderai.risk.threshold")}</dt><dd>{data["risk_threshold"]}</dd></div>'
                f'<div><dt>{self._label(labels, "orderai.risk.score")}</dt><dd>{data["risk_score"]}</dd></div>'
                f'<div><dt>{self._label(labels, "orderai.risk.decision")}</dt><dd>{decision}</dd></div>'
                f'<div><dt>{self._label(labels, "orderai.risk.reasons")}</dt><dd>{reasons}</dd></div></dl>'
            )
        retry = f'{data["retry_count"]}/{data["retry_limit"]}'
        return (
            '<dl class="mc-queue-data">'
            f'<div><dt>{self._label(labels, "orderai.queue.state")}</dt><dd>{escape(data["queue_state"])}</dd></div>'
            f'<div><dt>{self._label(labels, "orderai.queue.dedup")}</dt><dd>{escape(data["deduplication_state"])}</dd></div>'
            f'<div><dt>{self._label(labels, "orderai.queue.retry")}</dt><dd>{retry}</dd></div></dl>'
        )

    def _render_error(self, error: dict[str, Any] | None, labels: dict[str, str]) -> str:
        if not error:
            return ""
        return (
            f'<aside class="mc-inline-notice" aria-live="polite" data-error-code="{escape(error["code"])}">'
            f'<strong>{self._label(labels, "orderai.error.title")}</strong><p>{self._label(labels, error["message_key"])}</p></aside>'
        )

    def _render_actions(self, actions: list[dict[str, Any]], labels: dict[str, str]) -> str:
        if not actions:
            return ""
        rendered = []
        for action in actions:
            label = self._label(labels, action["label_key"])
            confirm = "true" if action.get("requires_confirmation") else "false"
            result_state = self._result_state(action)
            result_label = self._label(labels, f"orderai.status.{result_state}")
            target = self._target_screen(action["id"])
            rendered.append(
                f'<button class="mc-action-button" type="button" data-action-id="{escape(action["id"])}" '
                f'data-requires-confirmation="{confirm}" data-result-state="{escape(result_state)}" '
                f'data-result-label="{result_label}" data-action-label="{label}" data-target-screen="{target}" '
                f'data-confirm-label="{self._label(labels, "orderai.action.confirm")}" '
                f'data-cancel-label="{self._label(labels, "orderai.action.cancel")}">{label}</button>'
            )
        return f'<nav class="mc-screen-actions" aria-label="{self._label(labels, "orderai.actions.aria")}">{"".join(rendered)}</nav>'

    @staticmethod
    def _result_state(action: dict[str, Any]) -> str:
        if action["id"] in {"orderai.manual_retry", "orderai.simulate_retry"}:
            return "processing"
        return action.get("result_state", "success")

    @staticmethod
    def _target_screen(action_id: str) -> str:
        return {
            "orderai.view_risk_review": "orderai-risk_review",
            "orderai.view_queue": "orderai-queue",
            "orderai.return_to_parse": "orderai-parse_result",
        }.get(action_id, "")

    @staticmethod
    def _label(labels: dict[str, str], key: str | None) -> str:
        return escape(labels.get(key or "", key or ""))
