# API compatibility

Checked October 19, 2026 against the official UniFi Network 10.6.106 and Site Manager 1.0 documentation.

## Discovery sequence

1. Call `GET /v1/info` and record `applicationVersion`.
2. Fetch every `GET /v1/sites` page with `offset` and `limit`.
3. Probe site-scoped collection endpoints with `limit=1` on the first site.
4. When a device or client sample exists, probe its detail endpoint and latest device statistics.
5. Report each result as available, forbidden, unsupported, or unknown.
6. Fetch live data only after the user or agent selects a site.

The Network API has no documented endpoint that returns a complete capability manifest. Runtime GET probes are the evidence.

Discovery probes these collections: devices, clients, networks, Wi-Fi broadcasts, firewall policies, firewall zones, ACL rules, DNS policies, and WAN definitions. It also probes device details, latest device statistics, and client details when a sample ID exists. The other supported endpoints below are available through the shared client but are not part of discovery.

## Read endpoints supported by the shared client

| Data | Official Network path |
|---|---|
| Application version | `/v1/info` |
| Sites | `/v1/sites` |
| Adopted devices | `/v1/sites/{siteId}/devices` |
| Adopted device details | `/v1/sites/{siteId}/devices/{deviceId}` |
| Latest device statistics | `/v1/sites/{siteId}/devices/{deviceId}/statistics/latest` |
| Connected clients | `/v1/sites/{siteId}/clients` |
| Connected client details | `/v1/sites/{siteId}/clients/{clientId}` |
| Networks | `/v1/sites/{siteId}/networks` |
| Wi-Fi broadcasts | `/v1/sites/{siteId}/wifi/broadcasts` |
| Firewall policies | `/v1/sites/{siteId}/firewall/policies` |
| Firewall zones | `/v1/sites/{siteId}/firewall/zones` |
| ACL rules | `/v1/sites/{siteId}/acl-rules` |
| DNS policies | `/v1/sites/{siteId}/dns/policies` |
| Traffic matching lists | `/v1/sites/{siteId}/traffic-matching-lists` |
| LAGs | `/v1/sites/{siteId}/switching/lags` |
| Switch stacks | `/v1/sites/{siteId}/switching/switch-stacks` |
| WAN definitions | `/v1/sites/{siteId}/wans` |
| VPN servers | `/v1/sites/{siteId}/vpn/servers` |
| Site-to-site VPN tunnels | `/v1/sites/{siteId}/vpn/site-to-site-tunnels` |
| RADIUS profiles | `/v1/sites/{siteId}/radius/profiles` |
| Device tags | `/v1/sites/{siteId}/device-tags` |

Collections use the documented `offset`, `limit`, `count`, and `totalCount` shape. The client requests the documented maximum page size of 200 and stops at 10,000 records per operation.

## Remote connector limits

Ubiquiti documents these connector limits per console:

- Console firmware 5.0.3 or newer.
- 100 requests per minute.
- 25-second upstream timeout.
- 10 MB response body.

The client matches the 10 MB limit. Remote Network requests retry a `429` at most twice, waiting for the returned `Retry-After` value with a 60-second cap. An exhausted retry is reported to the caller. Local requests are not delayed or retried because Ubiquiti does not publish a local-Network rate limit in the cited documentation.

## Known data gaps

- `/clients` lists currently connected clients. It is not an offline-client history.
- The official API does not provide a single topology graph. The project derives edges only when returned records identify a parent device.
- The current snapshot is not a monitoring database. It cannot answer historical questions without an external collector.
- Endpoint availability changes by Network version. A `404` is reported and never replaced with an undocumented endpoint.

## Official sources

- [Current Network documentation](https://developer.ui.com/network)
- [Network 10.6.106 OpenAPI](https://developer.ui.com/network/v10.6.106/openapi.json)
- [Network filtering](https://developer.ui.com/network/v10.6.106/filtering)
- [Application info](https://developer.ui.com/network/v10.6.106/getinfo)
- [Local sites](https://developer.ui.com/network/v10.6.106/getsiteoverviewpage)
- [Site Manager 1.0](https://developer.ui.com/site-manager/v1.0.0/gettingstarted)
- [Site Manager 1.0 OpenAPI](https://developer.ui.com/site-manager/v1.0.0/openapi.json)
- [Official API overview](https://help.ui.com/hc/en-us/articles/30076656117655-Getting-Started-with-the-Official-UniFi-API)
