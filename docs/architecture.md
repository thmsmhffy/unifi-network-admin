# Architecture

The project has one API client and two thin interfaces.

```text
Agent Skill ── MCP tools ──┐
                           ├── UniFiClient ── ReadOnlyTransport ── UniFi Network API
Human or agent ── CLI ─────┘
```

`UniFiClient` owns API-root discovery, pagination, normalization, capability probes, snapshots, and topology inference. The CLI formats those models for a terminal. The MCP server returns the same Pydantic models as structured tool output.

## Connection modes

Local mode sends requests to:

```text
https://CONSOLE[:PORT]/proxy/network/integration/v1/...
```

Remote mode sends the same Network paths through the documented connector:

```text
https://api.ui.com/v1/connector/consoles/CONSOLE_ID/proxy/network/integration/v1/...
```

Setup uses the Site Manager `/v1/hosts` inventory when a remote console ID is not supplied. The saved profile then binds to that console.

## Trust boundaries

- A human creates profiles and selects the MCP process profile.
- The OS credential store or process environment supplies the API key.
- MCP tools cannot choose an origin, profile, CA file, or HTTP route.
- Constant route templates and validated IDs build every request.
- The transport rejects non-HTTPS origins, redirects, response bodies over 10 MB, and every method except `GET` or `HEAD`.
- Device names, SSIDs, IP addresses, and other controller data remain untrusted strings.

## Data claims

API records are labeled `verified`. A capability becomes verified only after a safe endpoint probe. A `403` is `forbidden`, a `404` or `405` is `unsupported`, and connection or server errors are `unknown`.

Topology nodes come from device and connected-client records. An edge appears only when one of those records names a known parent device. Edges are always labeled `inferred`, with the source field recorded as their basis.
