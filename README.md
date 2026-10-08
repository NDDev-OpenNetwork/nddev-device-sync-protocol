# nddev-device-sync-protocol

Public AGPL-3.0-only schemas for the NDDev OpenNetwork sync control plane.
This repository is the canonical wire contract between Flutter clients, Rust
core, server, agents and observability services.

The schemas contain no estate identifiers, credentials or production URLs.
Breaking changes require a new protocol major version and a compatibility
note in the central `nddev-device-sync` standards repository.

