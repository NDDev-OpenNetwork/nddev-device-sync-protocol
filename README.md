# nddev-device-sync-protocol

Public AGPL-3.0-only schemas for the NDDev OpenNetwork sync control plane.
This repository owns the canonical wire contracts consumed by Rust transports
for clients, server, agents and observability services. Flutter presentation
uses the Rust bridge; domain decisions remain in Core.

Schemas contain no private identifiers, credentials or deployment URLs.

| Contract | Status |
| --- | --- |
| `openapi/control-plane.yaml`, `contracts/v1/*-response.schema.json` | Current server health, readiness and AGPL source offer |
| `openapi/control-plane-v2.yaml`, `contracts/v2/control-plane.schema.json` | Email/GitHub/passkey identity, enrollment, sync, native vault keys and signed client observability; availability belongs to runtime adapters |
| `contracts/v2/screen.schema.json` | Owned RDS binding/finite view control for Rust Accounts/Server callers; native grant/capture/render acceptance belongs to those consumers |
| `contracts/v2/telemetry-*.schema.json` | Closed flat server-event envelope and bounded internal ingestion batch; delivery acceptance belongs to consumers |
| `openapi/sync-v3.yaml`, `contracts/v3/sync.schema.json` | Bounded history, original-row checkpoint transfer and explicit expiry outcomes; activation requires the coordinated reader/writer boundary |

Obsolete speculative v1 enrollment/sync/telemetry definitions remain in immutable
Git history and published tags, not as parallel active contracts. Breaking changes
use a new protocol major and a coordinated standards/consumer transition. Existing
release locks keep their original meaning; this work does not move tags.

Run `just setup`, then `just check` with the pinned Python, Node, Rust and Dart
tooling. Checks validate JSON Schema/OpenAPI semantics, rejection boundaries and
compiled Rust/Dart DTO round-trips. They do not prove a running authentication,
sync or telemetry service. See [development](docs/development.md) for generation
and [v2 semantics](docs/protocol-v2.md) for trust and consistency rules. The
[sync history lifecycle](docs/sync-lifecycle-v3.md) defines retained originals,
checkpoint installation and the transition from existing data.
