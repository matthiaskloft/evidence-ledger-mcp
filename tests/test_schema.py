import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from evidence_ledger_mcp.schema import load_schema, record_errors, schema_version
from evidence_ledger_mcp.server import schema_info, validate_record

RECORD: dict[str, Any] = {
    "id": "R-0001",
    "claim_id": "C-0001",
    "claim": "A claim.",
    "claim_type": "empirical",
    "contestable": False,
    "contestable_reason": "Example record",
    "anchor": {"exact": "A claim."},
    "key": "example2026",
    "no_identifier_reason": "Invented source for this test",
    "relation": "background",
    "retrieved_via": "pdf",
    "provenance": {"by_type": "human", "by": "Test", "date": "2026-10-30"},
}


def test_schema_is_valid_2020_12() -> None:
    Draft202012Validator.check_schema(load_schema())


def test_schema_version_is_semver() -> None:
    assert schema_version().count(".") == 2


def test_valid_record_has_no_errors() -> None:
    assert record_errors(RECORD) == []


def test_missing_field_is_reported() -> None:
    record = {k: v for k, v in RECORD.items() if k != "claim"}
    assert any("claim" in error for error in record_errors(record))


def test_tools_wrap_the_schema_module() -> None:
    assert schema_info() == {"schema_version": schema_version()}
    assert validate_record(RECORD) == []


def test_focus_requires_quote() -> None:
    assert any("quote" in error for error in record_errors({**RECORD, "quote_focus": "phrase"}))


def test_vendored_schema_matches_pin() -> None:
    directory = Path(__file__).resolve().parents[1] / "schema"
    pin = json.loads((directory / "UPSTREAM.json").read_text(encoding="utf-8"))
    assert pin["version"] == schema_version()
    assert pin["tag"] == f"schema-v{pin['version']}"
    assert len(pin["revision"]) == 40
    for name, expected in pin["files"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected, name
