set shell := ["bash", "-euo", "pipefail", "-c"]

default:
    @just --list

setup:
    python3 -m venv .venv
    .venv/bin/python -m pip install --require-hashes -r requirements.lock
    npm ci --ignore-scripts --no-fund

schema-check:
    .venv/bin/python scripts/validate.py

test:
    .venv/bin/python -m unittest discover -s tests -v

codegen-check:
    .venv/bin/python scripts/check-codegen.py

signatures-check:
    cargo fmt --all -- --check
    cargo test --workspace --locked --jobs 4
    cargo clippy --workspace --all-targets --locked --jobs 4 -- -D warnings

check: schema-check test codegen-check signatures-check
