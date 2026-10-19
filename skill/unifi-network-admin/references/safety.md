# Safety and changes

The shared transport permits `GET` and `HEAD` only. MCP exposes no raw request or mutation tool. This boundary applies even if the UniFi API key itself can write.

For a requested change:

1. Inspect the current object and its known references.
2. Describe the exact proposed change, reason, affected site and objects, expected effect, verification test, and recovery limits.
3. Call out management VLAN, gateway address, WAN, firewall, administrator access, adoption, and removal risk explicitly.
4. Tell the user that v0.1 cannot apply it. Do not imply that approval in chat unlocks a hidden path.
5. If the user will make the change in UniFi, offer a short verification checklist using read tools afterward.

The planned write contract is inspect, plan, validate, approve, apply, verify. Future approval must be one-time, short-lived, and bound to the exact profile, site, operation, payload, and current-state hash. UniFi does not guarantee an atomic transaction or rollback for every endpoint, so never promise recovery the API does not provide.
