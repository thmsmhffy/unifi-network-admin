"""Non-secret connection profiles."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

from platformdirs import user_config_path
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ConfigurationError
from .models import ConnectionMode

PROFILE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,255}$")
DEFAULT_CONFIG_PATH = user_config_path("unifi-network-admin") / "profiles.json"


def validate_profile_name(value: str) -> str:
    if not PROFILE_PATTERN.fullmatch(value):
        raise ValueError("use 1-64 lowercase letters, numbers, or hyphens")
    return value


def safe_segment(value: str, label: str = "identifier") -> str:
    if not ID_PATTERN.fullmatch(value) or "%" in value or "/" in value or "\\" in value:
        raise ConfigurationError(f"Invalid {label}")
    return quote(value, safe="")


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    mode: ConnectionMode
    url: str
    console_id: str | None = None
    ca_bundle: Path | None = None
    timeout_seconds: float = 20.0

    _validate_name = field_validator("name")(validate_profile_name)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme != "https":
            raise ValueError("URL must use https://")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("URL must contain a host and no embedded credentials")
        if parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("URL must be an origin such as https://192.168.1.1")
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("URL contains an invalid port") from exc
        return value.rstrip("/")

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if not 1 <= value <= 120:
            raise ValueError("timeout_seconds must be between 1 and 120")
        return value

    @model_validator(mode="after")
    def validate_mode(self) -> Profile:
        if self.mode is ConnectionMode.REMOTE:
            if self.url != "https://api.ui.com":
                raise ValueError("remote profiles always use https://api.ui.com")
            if not self.console_id:
                raise ValueError("remote profiles require console_id")
            safe_segment(self.console_id, "console ID")
        elif self.console_id:
            raise ValueError("console_id is only valid for remote profiles")
        return self

    def api_roots(self) -> list[str]:
        if self.mode is ConnectionMode.REMOTE:
            console = safe_segment(self.console_id or "", "console ID")
            return [
                f"https://api.ui.com/v1/connector/consoles/{console}/proxy/network/integration"
            ]
        return [
            f"{self.url}/proxy/network/integration",
        ]


class ProfileDocument(BaseModel):
    version: int = 1
    default_profile: str | None = None
    profiles: dict[str, Profile] = Field(default_factory=dict)


class ProfileStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_CONFIG_PATH

    def load(self) -> ProfileDocument:
        if not self.path.exists():
            return ProfileDocument()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return ProfileDocument.model_validate(data)
        except (OSError, ValueError) as exc:
            raise ConfigurationError(f"Cannot read profile file: {self.path}") from exc

    def save(self, document: ProfileDocument) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        payload = document.model_dump(mode="json")
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=self.path.parent, delete=False
            ) as handle:
                temp_name = handle.name
                json.dump(payload, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        except OSError as exc:
            if temp_name:
                Path(temp_name).unlink(missing_ok=True)
            raise ConfigurationError(f"Cannot write profile file: {self.path}") from exc

    def put(self, profile: Profile, *, make_default: bool = False) -> None:
        document = self.load()
        document.profiles[profile.name] = profile
        if make_default or document.default_profile is None:
            document.default_profile = profile.name
        self.save(document)

    def get(self, name: str | None = None) -> Profile:
        document = self.load()
        selected = name or document.default_profile
        if not selected:
            raise ConfigurationError("No profile is configured. Run: unifi-admin setup")
        try:
            return document.profiles[selected]
        except KeyError as exc:
            raise ConfigurationError(f"Unknown profile: {selected}") from exc

    def names(self) -> list[str]:
        return sorted(self.load().profiles)


def profile_from_environment(name: str = "default") -> Profile | None:
    url = os.getenv("UNIFI_URL")
    if not url:
        return None
    mode = ConnectionMode(os.getenv("UNIFI_MODE", "local").lower())
    console_id = os.getenv("UNIFI_CONSOLE_ID")
    ca_value = os.getenv("UNIFI_CA_BUNDLE")
    return Profile(
        name=name,
        mode=mode,
        url=url,
        console_id=console_id,
        ca_bundle=Path(ca_value) if ca_value else None,
    )


def load_profile(name: str | None = None, *, store: ProfileStore | None = None) -> Profile:
    configured_name = os.getenv("UNIFI_PROFILE")
    selected = name or configured_name or "default"
    if name is None:
        environment = profile_from_environment(selected)
        if environment:
            return environment
    return (store or ProfileStore()).get(name or configured_name)
