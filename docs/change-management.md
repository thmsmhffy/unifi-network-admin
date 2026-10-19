# Change management design

v0.1 cannot modify UniFi. There is no feature flag, hidden method, or MCP tool that unlocks writes.

The official API includes operations that replace whole objects, disconnect clients, and remove devices. A future write path must meet this contract before it ships.

## Required sequence

1. **Inspect:** Read the current object and every known reference.
2. **Plan:** Create an immutable plan with the profile, site, operation, redacted payload, impact, recovery notes, expiry, and current-state hash.
3. **Validate:** Check schema rules, API support, permissions, management access risk, and whether the plan has a verification test.
4. **Approve:** A human approves the exact plan through a separate local interface that the agent cannot call.
5. **Apply:** Re-read current state, reject drift, consume the one-time approval, and send one documented mutation.
6. **Verify:** Read the result, run the stated test, and record the outcome.

Approval must be bound to the plan digest, profile, site, operation, and expiry. It cannot authorize a category of later changes. Rejected, expired, changed, or already consumed plans must fail closed.

## Extra review

Changes to management networks, gateway addresses, WAN settings, firewall policy, administrator access, device adoption, or device removal need a recovery method that does not depend on the connection being changed.

UniFi does not promise atomic transactions or rollback for every operation. Recovery notes must describe what the API and hardware can do, not claim a rollback guarantee.

## First candidate

A small, reversible guest authorization action is a better first implementation than a network, WAN, or firewall rewrite. It still needs official schema validation, expiry, precondition checks, a one-time approval, audit output, and live tests against a disposable site.
