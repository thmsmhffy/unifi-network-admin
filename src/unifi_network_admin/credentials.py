"""API key lookup and OS keyring storage."""

from __future__ import annotations

import os

import keyring
from keyring.errors import KeyringError

from .config import validate_profile_name
from .errors import CredentialError

SERVICE_NAME = "unifi-network-admin"


def profile_environment_key(profile_name: str) -> str:
    validate_profile_name(profile_name)
    suffix = profile_name.replace("-", "_").upper()
    return f"UNIFI_API_KEY_{suffix}"


class CredentialStore:
    def get(self, profile_name: str) -> str:
        specific = os.getenv(profile_environment_key(profile_name))
        general = os.getenv("UNIFI_API_KEY")
        if specific or general:
            return specific or general or ""
        try:
            value = keyring.get_password(SERVICE_NAME, f"profile:{profile_name}")
        except KeyringError as exc:
            raise CredentialError(
                "The OS credential store is unavailable. Set UNIFI_API_KEY for this process."
            ) from exc
        if not value:
            raise CredentialError(
                f"No API key for profile '{profile_name}'. Run setup or set UNIFI_API_KEY."
            )
        return value

    def set(self, profile_name: str, api_key: str) -> None:
        if not api_key.strip():
            raise CredentialError("API key cannot be empty")
        try:
            keyring.set_password(SERVICE_NAME, f"profile:{profile_name}", api_key.strip())
        except KeyringError as exc:
            raise CredentialError(
                "The OS credential store is unavailable. The key was not written to disk; "
                "use UNIFI_API_KEY instead."
            ) from exc

    def delete(self, profile_name: str) -> None:
        try:
            keyring.delete_password(SERVICE_NAME, f"profile:{profile_name}")
        except KeyringError:
            return
