set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

json-check:
    python3 -m json.tool contracts/v1/device-enrollment.schema.json >/dev/null
    python3 -m json.tool contracts/v1/sync-operation.schema.json >/dev/null
    python3 -m json.tool contracts/v1/telemetry-event.schema.json >/dev/null

