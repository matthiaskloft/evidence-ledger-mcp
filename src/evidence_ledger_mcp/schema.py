"""Load the evidence ledger schema and validate records against it."""

from __future__ import annotations

import json
import re
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

SCHEMA_NAME = "evidence-ledger.schema.json"
# A source checkout has no packaged copy; the wheel gets one at build time.
REPO_SCHEMA = Path(__file__).resolve().parents[2] / "schema" / SCHEMA_NAME


@cache
def load_schema() -> dict[str, Any]:
    packaged = files("evidence_ledger_mcp") / SCHEMA_NAME
    text = packaged.read_text("utf-8") if packaged.is_file() else REPO_SCHEMA.read_text("utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def schema_version() -> str:
    """The schema version, read from its `$id` (`.../schema/X.Y.Z/...`)."""
    match = re.search(r"/schema/(\d+\.\d+\.\d+)/", load_schema()["$id"])
    if match is None:
        raise ValueError("schema $id carries no version")
    return match[1]


def header_errors(header: dict[str, Any]) -> list[str]:
    """Return one message per violation of the ledger header, empty if valid."""
    schema = {"$ref": "#/$defs/header", "$defs": load_schema()["$defs"]}
    validator = Draft202012Validator(schema)
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<header>'}: {error.message}"
        for error in sorted(validator.iter_errors(header), key=lambda e: list(e.absolute_path))
    ]


def record_errors(record: dict[str, Any]) -> list[str]:
    """Return one message per schema violation, empty if the record is valid."""
    validator = Draft202012Validator(load_schema())
    return [
        f"{'/'.join(map(str, error.absolute_path)) or '<record>'}: {error.message}"
        for error in sorted(validator.iter_errors(record), key=lambda e: list(e.absolute_path))
    ]
