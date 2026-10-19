"""Normalized public models shared by the CLI and MCP server."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ConnectionMode(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"


class Evidence(StrEnum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    UNAVAILABLE = "unavailable"


class CapabilityState(StrEnum):
    AVAILABLE = "available"
    FORBIDDEN = "forbidden"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


class Site(BaseModel):
    id: str
    name: str
    internal_reference: str | None = None
    evidence: Literal[Evidence.VERIFIED] = Evidence.VERIFIED


class ResourceRecord(BaseModel):
    kind: str
    id: str
    site_id: str
    name: str
    facts: dict[str, Any] = Field(default_factory=dict)
    evidence: Literal[Evidence.VERIFIED] = Evidence.VERIFIED


class ResourceList(BaseModel):
    kind: str
    site_id: str
    count: int
    items: list[ResourceRecord]
    evidence: Literal[Evidence.VERIFIED] = Evidence.VERIFIED


class Capability(BaseModel):
    name: str
    state: CapabilityState
    endpoint: str
    evidence: Evidence
    detail: str | None = None


class DiscoveryReport(BaseModel):
    profile: str
    connection: ConnectionMode
    application_version: str | None
    api_root: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sites: list[Site]
    capabilities: list[Capability]
    limitations: list[str] = Field(default_factory=list)


class SiteSnapshot(BaseModel):
    site: Site
    resources: dict[str, list[ResourceRecord]] = Field(default_factory=dict)
    unavailable: dict[str, str] = Field(default_factory=dict)


class NetworkSnapshot(BaseModel):
    profile: str
    application_version: str | None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sites: list[SiteSnapshot]
    limitations: list[str] = Field(default_factory=list)


class TopologyNode(BaseModel):
    id: str
    label: str
    kind: Literal["device", "client"]
    facts: dict[str, Any] = Field(default_factory=dict)
    evidence: Literal[Evidence.VERIFIED] = Evidence.VERIFIED


class TopologyEdge(BaseModel):
    source: str
    target: str
    relationship: str
    basis: str
    evidence: Literal[Evidence.INFERRED] = Evidence.INFERRED


class Topology(BaseModel):
    site_id: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    limitations: list[str] = Field(default_factory=list)


class WritePolicy(BaseModel):
    mode: Literal["observer"] = "observer"
    live_writes_available: Literal[False] = False
    rule: str = "The HTTP boundary permits GET and HEAD only."
    future_workflow: list[str] = Field(
        default_factory=lambda: ["inspect", "plan", "validate", "approve", "apply", "verify"]
    )
