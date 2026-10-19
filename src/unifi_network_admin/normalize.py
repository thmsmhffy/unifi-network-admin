"""Stable names for API objects whose schemas grow between Network versions."""

from __future__ import annotations

import re
from typing import Any

from .errors import InvalidResponse
from .models import ResourceRecord, Site

CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def snake_case(value: str) -> str:
    return CAMEL_BOUNDARY.sub("_", value).lower()


def normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {snake_case(str(key)): normalize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [normalize_value(item) for item in value]
    return value


def normalize_site(raw: dict[str, Any]) -> Site:
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise InvalidResponse("A site record is missing its ID")
    name = raw.get("name") or raw.get("internalReference") or identifier
    return Site(
        id=identifier,
        name=str(name),
        internal_reference=(
            str(raw["internalReference"]) if raw.get("internalReference") is not None else None
        ),
    )


def normalize_resource(kind: str, site_id: str, raw: dict[str, Any]) -> ResourceRecord:
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise InvalidResponse(f"A {kind} record is missing its ID")
    name = raw.get("name") or raw.get("displayName") or raw.get("macAddress") or identifier
    facts = normalize_value({key: value for key, value in raw.items() if key not in {"id", "name"}})
    return ResourceRecord(
        kind=kind,
        id=identifier,
        site_id=site_id,
        name=str(name),
        facts=facts,
    )
