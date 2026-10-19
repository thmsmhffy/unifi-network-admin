# UniFi Network Admin

UniFi Network Admin gives AI agents and people a shared read-only client and data model for UniFi Network. The command-line tool and MCP server expose the common discovery and diagnostic operations. The included Agent Skill tells an agent how to investigate network problems without guessing or changing the controller.

This is an independent open-source project. It is not made or supported by Ubiquiti.

## What works in v0.1

- Direct HTTPS access to the official local UniFi Network Integration API.
- Remote access through Ubiquiti's official Site Manager connector.
- Guided setup with API keys stored in the operating system credential store.
- Multi-site discovery, offset pagination, and endpoint capability checks.
- Devices, connected clients, networks, Wi-Fi broadcasts, firewall policy and zone data, ACLs, DNS policies, and WAN definitions where the installed Network version exposes them.
- Current snapshots and conservative topology inference.
- A standalone CLI, a stdio MCP server, and a portable Agent Skill.

Every HTTP request passes through a transport that accepts `GET` and `HEAD` only. The CLI and MCP server have no raw-request or mutation escape hatch.

## Install

Python 3.11 or newer is required. Install the latest commit from GitHub:

```bash
pipx install 'git+https://github.com/thmsmhffy/unifi-network-admin.git'
unifi-admin setup
```

To install a downloaded checkout instead, run this from its project directory:

```bash
pipx install .
unifi-admin setup
```

Contributors can use an editable virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Create an API key

For direct local access, open **UniFi Network > Integrations**. For remote access, create a key in **Site Manager > Settings > API Keys**. Ubiquiti displays a new key once, so save it when prompted.

Run setup and choose `local` or `remote`:

```bash
unifi-admin setup
```

The API key goes to the operating system credential store. The profile file contains only the console URL, connection type, console ID when remote, and an optional CA bundle path. If the machine has no keyring backend, setup leaves the key out of the file and asks you to set `UNIFI_API_KEY` for the process.

Local consoles often use a private certificate. The safest fix is to pass its CA certificate during setup:

```bash
unifi-admin setup --ca-bundle /path/to/unifi-ca.pem
```

For a one-off test, `--allow-insecure-tls` disables certificate checks for that command. The setting is never saved, and every later command needs the flag again.

## Use the CLI

```bash
unifi-admin doctor
unifi-admin sites
unifi-admin devices --site SITE_ID
unifi-admin device DEVICE_ID --site SITE_ID
unifi-admin device-stats DEVICE_ID --site SITE_ID
unifi-admin clients --site SITE_ID
unifi-admin client CLIENT_ID --site SITE_ID
unifi-admin networks --site SITE_ID
unifi-admin wifi --site SITE_ID
unifi-admin firewall --site SITE_ID
unifi-admin topology --site SITE_ID
unifi-admin snapshot > snapshot.json
```

Commands that list data support `--json`. If the controller has one site, `--site` is optional.

Use separate profiles for unrelated deployments:

```bash
unifi-admin setup --profile office
unifi-admin doctor --profile office
```

## Connect an MCP client

Install the package first, then configure a stdio server in the MCP client:

```json
{
  "mcpServers": {
    "unifi-network-admin": {
      "command": "unifi-admin-mcp",
      "args": ["--profile", "office"]
    }
  }
}
```

The process binds to one profile at startup. Its tools accept site and resource IDs, not URLs, profile names, credential paths, or API keys. Anyone who can run the MCP process as your operating-system user can use that profile's read access.

The Python package includes the Agent Skill. Copy it into the skills directory supported by your agent:

```bash
unifi-admin export-skill /path/to/agent/skills
```

From a source checkout, you can instead copy [`skill/unifi-network-admin`](skill/unifi-network-admin) directly. Configure the MCP server separately. If MCP is unavailable but the agent can run local commands, the Skill uses `unifi-admin ... --json` as a fallback.

`export-skill` will not overwrite an existing skill. To update it, rename the old `unifi-network-admin` directory, export the new copy, compare any local edits, then remove the backup after the new skill works.

## API compatibility

Ubiquiti's local Network API is version-specific. This release was checked on October 19, 2026 against the current Network 10.6.106 documentation and the Site Manager 1.0 API. It starts with `/v1/info`, lists all `/v1/sites` pages, and probes safe GET endpoints instead of assuming that a feature exists.

Older Network versions can expose fewer resources. The client reports an endpoint as available, forbidden, unsupported, or unknown. It does not fall back to the undocumented legacy `/api/s/...` interface.

Official references:

- [Ubiquiti's API overview](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API)
- [UniFi Network 10.6.106 API](https://developer.ui.com/network/v10.6.106/gettingstarted)
- [UniFi Network OpenAPI document](https://developer.ui.com/network/v10.6.106/openapi.json)
- [Site Manager API 1.0](https://developer.ui.com/site-manager/v1.0.0/gettingstarted)
- [Site Manager OpenAPI document](https://developer.ui.com/site-manager/v1.0.0/openapi.json)

See [API compatibility](docs/api-compatibility.md) for the endpoint map and known limits.

## Writes and approvals

v0.1 does not change UniFi configuration. That is a code boundary, not a prompt instruction. The official API includes destructive operations, including device removal and full configuration replacements, so adding one safe write requires more than exposing another endpoint.

The future contract is documented in [change management](docs/change-management.md): inspect, plan, validate, approve, apply, and verify. An approval will be short-lived, one-time, and bound to the exact profile, site, payload, and current-state hash. No live write will ship without a documented endpoint, drift check, audit record, and recovery notes.

## Project map

```text
src/unifi_network_admin/     shared client, CLI, and MCP server
skill/unifi-network-admin/   portable Agent Skill
tests/                       unit, MCP, security, and opt-in live tests
docs/                        API, security, architecture, and change design
```

Read [security](docs/security.md) before running the MCP server on a shared machine. Development commands are in [development](docs/development.md).
