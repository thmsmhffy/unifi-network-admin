# Data interpretation

Use four evidence labels.

- **Reported:** Stated by the user or another human source; not yet verified through the API.
- **Verified:** Returned directly by a successful official API read during this investigation.
- **Inferred:** Derived from verified fields. Name the fields and reasoning.
- **Unavailable:** Not exposed, unsupported, forbidden, stale, failed, or outside the current snapshot.

An `available` capability means its safe GET probe succeeded. `forbidden` means the endpoint was present but the key received `403`. `unsupported` means the endpoint returned `404` or `405`. `unknown` covers transport, rate-limit, malformed-response, and server failures. Do not turn `unknown` into `unsupported`.

A user report remains reported even when it guides the investigation. The API can corroborate or contradict parts of it, but do not relabel the original claim as verified.

The clients endpoint returns currently connected clients. It cannot prove that a client never connected, how it behaved last week, or how often it roamed.

Topology nodes are verified inventory. Edges are inferred only from returned attachment fields and include their basis. No edge means the list response did not support that claim; it does not prove that two devices are physically unrelated.

A snapshot records one point in time. Historical comparisons require two timestamped snapshots or an external metrics store.
