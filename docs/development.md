# Development workflow

Use the pinned toolchain and the repository's `just` recipes. Keep runtime
credentials, private estate data and live telemetry outside this repository.

`main` and `dev` are permanent branches. Make scoped changes on a working
branch, submit a pull request to `dev`, and promote reviewed changes from
`dev` to `main`. Use Conventional Commits and signed commits. Do not delete
permanent branches or rewrite published history.

The `NDS checks / quality` job runs on GitHub-hosted Ubuntu with read-only
repository permissions and immutable action pins. It checks this repository's
current foundation. A green result is not deployment, release, integration or
cross-platform acceptance. Full release gates remain those in the locked
central standards.

## Standards compatibility

The standards lock adopts published `v0.0.1-alpha.9`, source commit
`16a477beac6127adf73ef102df74a48451d607f1`, which specifies both owner email OTP
and GitHub sign-in. The planned v2 major is a new adoption boundary, not a claim
of compatibility with old v1 planning schemas or their GitHub-only identity lock.
Published tags retain their original meaning. Runtime consumers pin a reviewed
protocol source and prove implemented behavior before advertising v2 capability;
this schema/tooling change alone is not a protocol release or working backend.

## Validation and projections

`requirements.lock` pins and hashes the complete Python validator environment;
`package-lock.json` pins quicktype and its dependencies. Update Python resolution
with `uv pip compile --generate-hashes -o requirements.lock requirements.in`,
then run the complete gate. Tool versions are deliberate changes, not floating
CI installs. The small Rust codegen acceptance harness uses its own locked
dependencies in a disposable directory; this remains a schema repository.

JSON Schema 2020-12 validation uses `jsonschema`, with explicit date-time, email
and URI format validators. `openapi-spec-validator` checks OpenAPI 3.1 semantics.
References resolve only inside the repository; missing/remote references fail.

Generate into the owning consumer, never maintain duplicate DTOs here:

```sh
node scripts/generate-dtos.mjs rust health OUTPUT.rs
node scripts/generate-dtos.mjs rust auth OUTPUT.rs
node scripts/generate-dtos.mjs dart auth OUTPUT.dart
node scripts/generate-dtos.mjs rust telemetry OUTPUT.rs
```

`ready` and `source` are additional baseline profiles. Auth emits only the named
identity messages used by the server slice; enrollment/sync have no generated
runtime scaffolding. Telemetry currently has only a Rust consumer. Consumers
pin the protocol source commit/release and regenerate through this exact script;
headers record schema, generator-script and generator-lock hashes. Consumer formatters may run
after generation, reproducibly, without manual DTO changes.

Quicktype owns type projection. A narrow reviewed Rust profile projects closed
objects as `deny_unknown_fields`, omits absent optional fields and disables
`Debug` derives. Timestamps remain exact wire strings in both languages.
Generated DTOs do not enforce lengths, formats, byte budgets, authorization,
cryptography or transactional invariants: consumers enforce those at their
boundary. The source-schema rejection suite and the compiled DTO suite are
separate evidence. No custom schema engine or client framework is introduced.

Tool ownership is this repository: validators and quicktype serve contract
acceptance, use their Apache-2.0/MIT-compatible tooling licenses and are updated
only with lock review and the same semantic/compile checks. Remove a generator
profile when its last consumer disappears; replace tooling only with equivalent
contract and round-trip evidence.

The flat telemetry schema follows the current server producer, including its
bounded fixed error-class strings. It allows no arbitrary attributes/message
bag. The ingestion adapter separately enforces 16 KiB per event and at most 100
events per batch, authenticates its internal service credential and bounds queue,
retention and label cardinality. Device authorization belongs at the central
server gateway; this schema is not an authorization mechanism.

Actual identity delivery fields distinguish provider acceptance from mailbox
delivery (`unverified`). The optional producer UUID/sequence fields form a pair;
sequence starts at one and ends at the JSON-safe integer limit. An absent pair
means unsequenced, not loss-free. Gaps/reordering are observations, not exact
confirmed drop counts. Validate real process NDJSON without retaining or printing
event values using `.venv/bin/python scripts/validate-events.py < PRIVATE_CAPTURE`.
