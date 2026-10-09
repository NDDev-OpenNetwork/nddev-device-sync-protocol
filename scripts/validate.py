"""Validate canonical schemas and OpenAPI semantics without remote references."""

import json
from pathlib import Path
from urllib.parse import unquote, urldefrag

from jsonschema import Draft202012Validator, FormatChecker
from openapi_spec_validator import validate as validate_openapi
from referencing import Registry, Resource
import yaml

ROOT = Path(__file__).resolve().parents[1]


def references(value):
    if isinstance(value, dict):
        if "$ref" in value:
            yield value["$ref"]
        for child in value.values():
            yield from references(child)
    elif isinstance(value, list):
        for child in value:
            yield from references(child)


def schemas():
    if not {"date-time", "email", "uri"} <= FormatChecker.checkers.keys():
        raise ValueError("Required format validators are missing; install the locked tools")
    documents = {}
    for path in sorted((ROOT / "contracts").rglob("*.schema.json")):
        document = json.loads(path.read_text())
        expected_id = "https://nddev.ai/schemas/nddev-device-sync/" + path.relative_to(ROOT / "contracts").as_posix()
        if document.get("$id") != expected_id:
            raise ValueError("Schema identity must match its canonical repository path")
        Draft202012Validator.check_schema(document)
        if document["$id"] in documents:
            raise ValueError("Duplicate schema identity")
        documents[document["$id"]] = document
    registry = Registry().with_resources(
        (identity, Resource.from_contents(document))
        for identity, document in documents.items()
    )
    for identity, document in documents.items():
        for reference in references(document):
            registry.resolver(identity).lookup(reference)
    return documents, registry


def validator(document, registry, definition=None):
    target = document if definition is None else {
        "$ref": document["$id"] + "#/$defs/" + definition
    }
    return Draft202012Validator(target, registry=registry, format_checker=FormatChecker())


def validate_api(document, path):
    # OpenAPI's validator owns semantic validation; this guard prevents network
    # fetches and references escaping the reviewed source tree.
    for reference in references(document):
        location, fragment = urldefrag(reference)
        if ":" in location or location.startswith("//"):
            raise ValueError("OpenAPI references must be local")
        target = (path.parent / unquote(location)).resolve() if location else path
        if not target.is_relative_to(ROOT) or not target.is_file():
            raise ValueError("OpenAPI reference escapes or misses the source tree")
        if target.relative_to(ROOT).parts[0] not in {"contracts", "openapi"} or target.suffix not in {".json", ".yaml"}:
            raise ValueError("OpenAPI references may read only canonical contract files")
        resolved = yaml.safe_load(target.read_text())
        if fragment:
            if not fragment.startswith("/"):
                raise ValueError("Expected a JSON Pointer reference")
            for part in fragment[1:].split("/"):
                resolved = resolved[unquote(part).replace("~1", "/").replace("~0", "~")]
    validate_openapi(document, base_uri=path.as_uri())


def main():
    documents, _ = schemas()
    paths = sorted((ROOT / "openapi").glob("*.yaml"))
    for path in paths:
        validate_api(yaml.safe_load(path.read_text()), path)
    print(f"Validated {len(documents)} JSON Schemas and {len(paths)} OpenAPI documents.")


if __name__ == "__main__":
    main()
