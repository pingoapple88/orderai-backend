#!/usr/bin/env python3
"""Validate the provider-neutral C6 Gate packet without contacting external systems."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

REQUIRED_HEADINGS = (
    "## 1. Packet identity and operating boundary",
    "## 2. Common owner packet schema",
    "## 3. Payment / refund gate",
    "## 4. Invoice / accounting / tax gate",
    "## 5. Yunding / Jiezhou ERP staging gate",
    "## 6. LINE / OrderAI gate",
    "## 7. iMin / device gate",
    "## 8. Railway / DNS / TLS gate",
    "## 9. Backup / DR gate",
    "## 10. Production approval gate",
    "## 11. Cross-chat status and reviewer handoff record",
    "## 12. Delivery checklist and explicit next exit",
)
REQUIRED_TERMS = (
    "mandatory fields",
    "stop conditions",
    "reviewer handoff",
    "[TODO: 待人工確認]",
    "sha256",
    "rollback",
    "idempot",
    "CROSS_CHAT_STATUS_UPDATE",
)
# These are generic platform-shadow indicators that must never enter the packet.
FORBIDDEN_SHADOW = re.compile(
    r"(?i)(built\s+with\s+[A-Za-z][\w.-]*(?:\s+[A-Za-z][\w.-]*){0,3}|"
    r"generated\s+by\s+[A-Za-z][\w.-]*(?:\s+[A-Za-z][\w.-]*){0,3}|"
    r"(?:platform|vendor|ai)[_-]?generated)"
)
SECRET_PATTERNS = (
    re.compile(r"(?i)\b(api[_ -]?key|access[_ -]?token|secret[_ -]?key|private[_ -]?key|password)\s*[:=]\s*[^\s`]+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def fenced_blocks(text: str, language: str) -> list[str]:
    pattern = re.compile(rf"```{language}\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
    return pattern.findall(text)


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    if not text.endswith("\n"):
        errors.append("document must end with a newline")
    if "\t" in text:
        errors.append("document contains tab characters")
    for heading in REQUIRED_HEADINGS:
        if heading not in text:
            errors.append(f"missing required heading: {heading}")
    for term in REQUIRED_TERMS:
        if term not in text:
            errors.append(f"missing required term: {term}")
    if text.count("[TODO: 待人工確認]") < 20:
        errors.append("packet must preserve unresolved fields as [TODO: 待人工確認]")

    # Lightweight Markdown sanity checks that do not rewrite or normalize content.
    in_fence = False
    fence_language = ""
    for number, line in enumerate(lines, 1):
        if line.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_language = line[3:].strip().lower()
            else:
                in_fence = False
                fence_language = ""
        if line.startswith("| ") and line.count("|") < 3:
            errors.append(f"line {number}: malformed Markdown table row")
    if in_fence:
        errors.append("unclosed fenced code block")

    for block in fenced_blocks(text, "yaml"):
        try:
            parsed = yaml.safe_load(block)
        except yaml.YAMLError as exc:
            errors.append(f"embedded YAML parse error: {exc}")
            continue
        if not isinstance(parsed, dict) or parsed.get("work_item_id") != "C6-PROVIDER-GATE-PACKET-001":
            errors.append("embedded YAML must be a mapping for this work item")
    for block in fenced_blocks(text, "json"):
        try:
            parsed = json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"embedded JSON parse error: {exc}")
            continue
        if not isinstance(parsed, dict) or "evidence_id" not in parsed:
            errors.append("embedded JSON must contain evidence_id")

    shadow_match = FORBIDDEN_SHADOW.search(text)
    if shadow_match:
        errors.append(f"platform-shadow term found: {shadow_match.group(0)!r}")
    for pattern in SECRET_PATTERNS:
        match = pattern.search(text)
        if match:
            errors.append(f"secret-like material found: {match.group(0)[:48]!r}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    if not args.path.is_file():
        print(f"ERROR: missing packet: {args.path}", file=sys.stderr)
        return 2
    errors = validate(args.path)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {args.path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
