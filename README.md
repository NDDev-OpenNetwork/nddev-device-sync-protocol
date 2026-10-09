# nddev-device-sync-protocol

Public AGPL-3.0-only schemas for the NDDev OpenNetwork sync control plane.
This repository is the canonical wire contract between Flutter clients, Rust
core, server, agents and observability services.

Schemas contain no private identifiers, credentials or deployment URLs.

| Contract | Status |
| --- | --- |
| `openapi/control-plane.yaml`, `contracts/v1/*-response.schema.json` | Current server health, readiness and AGPL source offer |
| `openapi/control-plane-v2.yaml`, `contracts/v2/control-plane.schema.json` | Planned email/GitHub identity, sessions, enrollment and sync; not implemented capability discovery |
| `contracts/v2/telemetry-*.schema.json` | Closed flat server-event envelope and bounded internal ingestion batch; delivery acceptance belongs to consumers |

Obsolete speculative v1 enrollment/sync/telemetry definitions remain in immutable
Git history and published tags, not as parallel active contracts. Breaking changes
use a new protocol major and a coordinated standards/consumer transition. Existing
release locks keep their original meaning; this work does not move tags.

Run `just setup`, then `just check` with the pinned Python, Node, Rust and Dart
tooling. Checks validate JSON Schema/OpenAPI semantics, rejection boundaries and
compiled Rust/Dart DTO round-trips. They do not prove a running authentication,
sync or telemetry service. See [development](docs/development.md) for generation
and [v2 semantics](docs/protocol-v2.md) for trust and consistency rules.
