# nddev-device-sync-protocol working contract

Keep schemas generic, versioned and free of private estate data. Every event
must define redaction expectations, idempotency behavior and compatibility
rules. Generated clients belong in consuming repositories; this repository
owns the source schemas.

Follow the locked central engineering standard. Keep the smallest versioned
schema that preserves idempotency, redaction, compatibility and explicit
failure outcomes. Do not add fields without an owner and migration rule.
