"""Validate real producer NDJSON from stdin without printing event values."""
import json
import sys
from validate import schemas, validator


def reject_constant(_):
    raise ValueError("non-JSON number")


def main():
    documents, registry = schemas()
    schema = documents["https://nddev.ai/schemas/nddev-device-sync/v2/telemetry-event.schema.json"]
    check = validator(schema, registry)
    count = 0
    for line in sys.stdin.buffer:
        if not line.strip():
            continue
        if len(line.rstrip(b"\r\n")) > 16384:
            raise SystemExit(f"Event {count + 1}: encoded byte budget exceeded")
        try:
            event = json.loads(line, parse_constant=reject_constant)
        except (ValueError, UnicodeError):
            raise SystemExit(f"Event {count + 1}: invalid JSON") from None
        error = next(check.iter_errors(event), None)
        if error is not None:
            raise SystemExit(f"Event {count + 1}: schema constraint {error.validator}")
        count += 1
    if count == 0:
        raise SystemExit("No producer events received")
    print(f"Validated {count} actual producer events; no values retained or printed.")


if __name__ == "__main__":
    main()
