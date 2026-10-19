from __future__ import annotations

from pathlib import Path

import yaml

SKILL_ROOT = Path(__file__).parents[1] / "skill" / "unifi-network-admin"


def test_skill_manifest_and_ui_metadata_are_complete() -> None:
    text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    _, front_matter, body = text.split("---", 2)
    metadata = yaml.safe_load(front_matter)
    assert metadata["name"] == "unifi-network-admin"
    assert "[TODO" not in text
    assert "discover" in metadata["description"].lower()
    assert "read-only" in body.lower()

    ui = yaml.safe_load((SKILL_ROOT / "agents" / "openai.yaml").read_text())
    assert ui["interface"]["default_prompt"].startswith("Use $unifi-network-admin")
    assert ui["policy"]["allow_implicit_invocation"] is True


def test_every_linked_skill_reference_exists() -> None:
    for name in ("cli-fallback.md", "data-interpretation.md", "diagnostics.md", "safety.md"):
        assert (SKILL_ROOT / "references" / name).is_file()
