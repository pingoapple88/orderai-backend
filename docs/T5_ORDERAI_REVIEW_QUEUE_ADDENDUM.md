# T5 OrderAI Review Queue Addendum

## Delivery boundary

This addendum supplies only five-locale `DEMO_MOCK` contracts and synthetic fixtures for a consumer request-draft view, an owner review queue, and a provider-neutral confirmation-handoff placeholder. It does not create an OrderAI, StallPay, or ERP order; connect an endpoint; write a database; add an event; or change OAuth, payment, invoice, subscription, parser, risk, or queue runtime behavior.

## Audience separation

| Audience | Screen | Permitted presentation | Explicitly hidden or blocked |
|---|---|---|---|
| Consumer | `orderai.consumer_conversation` | Conversation, product／quantity confirmation, pickup prompt, draft notice, notification and next action | Confidence, threshold, risk／queue state, dead letter, audit reference, ERP field and raw PII |
| Owner | `orderai.review_queue` | Redacted draft summary, confidence／threshold, low-confidence, shortage／conflict, status, audit reference and `save_draft` | Automatic approval, order creation, provider retry, StallPay submission and ERP write |
| T2／central owner | `orderai.confirmation_handoff` | Provider-neutral draft view-model field names only | Endpoint, HTTP method, payload contract, idempotency transport, formal creation responsibility and ERP write remain `[TODO]`／`BLOCKED` |

## Fail-closed rules

The confidence threshold is `0.85`. A value below it, an unmatched item, shortage, conflict, unknown outcome, or missing authorization cannot create a formal order. The owner view maps these to `manual_review` or `blocked`; the only synthetic state-changing presentation action is `save_draft`. No retry action is exposed. Consumer status projections avoid exposing internal confidence and queue fields.

## Cross-team requests

`XREQ-EXPO-0002` remains a response obligation for the T1 Demo mounting requirements. `XREQ-EXPO-0003` requests T2／central confirmation of formal order-creation responsibility, endpoint, normalized payload, idempotency behavior and acknowledged queue semantics. `XREQ-EXPO-0005` remains required before any formal service connection. Until all are resolved, `orderai.confirmation_handoff` must render `blocked` with `save_draft_only`.
