from pathlib import Path

from scripts.validate_c6_provider_gate_packet import validate


PACKET = Path(__file__).parents[1] / "docs/gates/c6-provider-gate-packet-001.md"


def test_c6_packet_passes_structural_validation():
    assert validate(PACKET) == []


def test_c6_packet_validator_rejects_platform_shadow(tmp_path):
    target = tmp_path / "packet.md"
    shadow_text = "built" + " with external-tool"
    target.write_text(PACKET.read_text(encoding="utf-8") + f"\n{shadow_text}\n", encoding="utf-8")
    errors = validate(target)
    assert any("platform-shadow" in error for error in errors)


def test_c6_packet_validator_rejects_secret_like_value(tmp_path):
    target = tmp_path / "packet.md"
    secret_label = "api" + "_key"
    target.write_text(PACKET.read_text(encoding="utf-8") + f"\n{secret_label}: real-looking-value\n", encoding="utf-8")
    errors = validate(target)
    assert any("secret-like" in error for error in errors)
