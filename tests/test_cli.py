from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

import unifi_network_admin.cli as cli
from unifi_network_admin.cli import app
from unifi_network_admin.models import Site

runner = CliRunner()


def test_help_names_read_only_purpose() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "without changing it" in result.stdout


def test_write_policy_is_explicit() -> None:
    result = runner.invoke(app, ["write-policy"])
    assert result.exit_code == 0
    assert '"live_writes_available": false' in result.stdout
    assert '"mode": "observer"' in result.stdout


def test_json_output_is_not_wrapped_or_interpreted(monkeypatch) -> None:
    name = "[red]literal[/red] " + "x" * 120

    async def fake_sites(profile, allow_insecure_tls):
        return [Site(id="site-1", name=name)]

    monkeypatch.setattr(cli, "_sites", fake_sites)
    result = runner.invoke(app, ["sites", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)[0]["name"] == name


def test_human_output_treats_network_names_as_literal(monkeypatch) -> None:
    async def fake_sites(profile, allow_insecure_tls):
        return [Site(id="site-1", name="[red]literal[/red]")]

    monkeypatch.setattr(cli, "_sites", fake_sites)
    result = runner.invoke(app, ["sites"])

    assert result.exit_code == 0
    assert "[red]literal[/red]" in result.stdout


def test_setup_accepts_profile_specific_environment_key_and_resolves_ca(
    monkeypatch, tmp_path
) -> None:
    seen: list[str] = []
    saved_profiles = []
    ca_bundle = tmp_path / "console-ca.pem"
    ca_bundle.write_text("test certificate")

    async def fake_discover(profile, api_key, *, allow_insecure_tls):
        seen.append(api_key)
        return SimpleNamespace(application_version="10.6.106", sites=[])

    class FakeProfileStore:
        def put(self, profile, *, make_default):
            saved_profiles.append(profile)

    monkeypatch.setattr(cli, "_discover_with", fake_discover)
    monkeypatch.setattr(cli, "ProfileStore", FakeProfileStore)
    monkeypatch.setenv("UNIFI_API_KEY_OFFICE", "profile-key")
    monkeypatch.delenv("UNIFI_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        app,
        [
            "setup",
            "--profile",
            "office",
            "--mode",
            "local",
            "--url",
            "https://console.test",
            "--ca-bundle",
            "console-ca.pem",
            "--no-store-key",
        ],
    )

    assert result.exit_code == 0
    assert seen == ["profile-key"]
    assert saved_profiles[0].ca_bundle == ca_bundle.resolve()


def test_export_skill_copies_bundled_files(tmp_path) -> None:
    result = runner.invoke(app, ["export-skill", str(tmp_path)])

    assert result.exit_code == 0
    exported = tmp_path / "unifi-network-admin"
    assert (exported / "SKILL.md").is_file()
    assert (exported / "agents" / "openai.yaml").is_file()
    assert (exported / "references" / "safety.md").is_file()

    repeated = runner.invoke(app, ["export-skill", str(tmp_path)])
    assert repeated.exit_code != 0
    assert "already exists" in repeated.output
