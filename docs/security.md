# Security

## Credentials

The CLI never accepts an API key as an argument. Setup reads it from a hidden prompt or `UNIFI_API_KEY`, tests the connection, and asks the operating system credential store to save it under the profile name. The JSON profile file never contains secrets.

Headless systems can use either:

```bash
export UNIFI_API_KEY='...'
export UNIFI_PROFILE='office'
```

or a profile-specific variable such as `UNIFI_API_KEY_OFFICE`. The profile-specific value wins.

Environment variables are a process-level fallback, not encrypted storage. Keep them out of shell history, checked-in files, service definitions with broad read permissions, and MCP configuration JSON.

## TLS

Certificate verification is on by default. A private CA bundle is the preferred fix for a local console certificate:

```bash
unifi-admin setup --ca-bundle /path/to/ca.pem
```

`--allow-insecure-tls` applies to one command or MCP process. It prints a warning and is never saved. Redirects are disabled so a credential-bearing request cannot move to another origin.

## Read-only boundary

The package has no write-capable client method. `ReadOnlyTransport` checks the method before making a request and accepts `GET` and `HEAD` only. The MCP schema exposes no create, update, delete, apply, action, or raw-request tool.

An API key may still have write access in UniFi. v0.1's safety comes from the application boundary, not from an assumption about the key's server-side permissions.

## MCP access

The stdio server trusts the operating-system user and the MCP host that starts it. It binds to one profile. Tool inputs cannot pick another profile or controller.

Do not run the server under a shared account. Do not expose it through an unauthenticated network transport. Keep stdout reserved for MCP messages; the server sends its one TLS warning to stderr.

## Data handling

Network snapshots can contain device names, client names, MAC addresses, IP addresses, SSIDs, VLANs, and policy data. Treat exported JSON as sensitive network documentation. The project does not send that data anywhere except the configured UniFi endpoint and the local caller.

Please report vulnerabilities privately using the process in [`SECURITY.md`](../SECURITY.md).
