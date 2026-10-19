from __future__ import annotations

import json
import stat

import pytest
from pydantic import ValidationError

from unifi_network_admin.config import Profile, ProfileStore, load_profile, safe_segment
from unifi_network_admin.credentials import CredentialStore, profile_environment_key
from unifi_network_admin.errors import ConfigurationError
from unifi_network_admin.models import ConnectionMode


def test_profile_requires_safe_https_origin() -> None:
    for bad_url in (
        "http://192.168.1.1",
        "https://user:pass@example.test",
        "https://example.test/network",
        "https://example.test?key=value",
        "https://example.test/#fragment",
    ):
        with pytest.raises(ValidationError):
            Profile(name="home", mode="local", url=bad_url)


def test_remote_profile_has_fixed_origin_and_documented_root() -> None:
    profile = Profile(
        name="remote",
        mode=ConnectionMode.REMOTE,
        url="https://api.ui.com",
        console_id="console:123",
    )
    assert profile.api_roots() == [
        "https://api.ui.com/v1/connector/consoles/console%3A123/proxy/network/integration"
    ]
    with pytest.raises(ValidationError):
        Profile(
            name="bad",
            mode="remote",
            url="https://example.test",
            console_id="console-1",
        )


def test_safe_segment_rejects_route_injection() -> None:
    for value in ("../sites", "%2f", "a/b", "a\\b", "x\r\nHeader:y"):
        with pytest.raises(ConfigurationError):
            safe_segment(value)


def test_profile_store_is_secret_free_and_private(tmp_path) -> None:
    path = tmp_path / "profiles.json"
    store = ProfileStore(path)
    store.put(Profile(name="home", mode="local", url="https://192.168.1.1"))

    payload = json.loads(path.read_text())
    assert "api_key" not in json.dumps(payload).lower()
    assert store.get().name == "home"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_profile_specific_environment_key_wins(monkeypatch) -> None:
    monkeypatch.setenv("UNIFI_API_KEY", "general")
    monkeypatch.setenv(profile_environment_key("lab-east"), "specific")
    assert CredentialStore().get("lab-east") == "specific"


def test_profile_names_cannot_share_an_environment_key() -> None:
    assert profile_environment_key("lab-east") == "UNIFI_API_KEY_LAB_EAST"
    for ambiguous in ("lab_east", "lab.east", "Lab-east"):
        with pytest.raises(ValueError):
            profile_environment_key(ambiguous)


def test_explicit_profile_is_not_redirected_by_environment(tmp_path, monkeypatch) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.put(Profile(name="office", mode="local", url="https://office.test"))
    monkeypatch.setenv("UNIFI_URL", "https://other.test")
    assert load_profile("office", store=store).url == "https://office.test"
