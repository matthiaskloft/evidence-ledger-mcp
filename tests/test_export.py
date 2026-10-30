from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import export, ledger

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
QUOTE = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
PREFIX = "In the second year of the trial,"
OTHER = "A different sentence from another source entirely"
RECORD: dict[str, Any] = {
    "claim": "Ledgers cut unchecked citations.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "cut unchecked citations"},
    "key": "exampleStudy2026",
    "no_identifier_reason": "Invented source for this test",
    "locator": {"page": 4, "chunk": {"index": 7, "sha256": "0" * 64}},
    "quote": QUOTE,
    "quote_prefix": PREFIX,
    "quote_suffix": "and authors kept the habit.",
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    return target


def add(path: str, **changes: Any) -> dict[str, Any]:
    return ledger.add_record(path, {**RECORD, **changes}, PROVENANCE)


def out_of(path: str, name: str = "out.jsonl") -> str:
    return str(Path(path).parent / name)


@pytest.mark.parametrize(
    ("quote", "masked"),
    [
        ("", "…"),
        ("one", "…"),
        ("one two three", "…"),
        ("one two three four", "one … four"),
        ("one two three four five six seven", "one … seven"),
        ("a b c d e f g h", "a b … g h"),
        ("a b c d e f g h i j k l m n", "a b c … l m n"),
    ],
)
def test_mask_quote(quote: str, masked: str) -> None:
    assert export.mask_quote(quote) == masked


def test_export_record_levels() -> None:
    record = {**RECORD, "quote_hash": ledger.quote_hash(QUOTE)}
    full = export.export_record(record, "full")
    assert full["locator"] == {"page": 4}
    assert full["quote"] == QUOTE
    assert "chunk" in record["locator"]

    masked = export.export_record(record, "masked")
    assert masked["quote"] == "Ledger records … per manuscript"
    assert not {"quote_prefix", "quote_suffix"} & masked.keys()
    assert masked["locator"] == {"page": 4}
    assert masked["quote_hash"] == record["quote_hash"]

    located = export.export_record(record, "locator")
    assert not set(export.SOURCE_FIELDS) & located.keys()
    assert located["quote_hash"] == record["quote_hash"]
    assert located["claim"] == record["claim"]


def test_export_record_without_quote() -> None:
    record = {"id": "R-0001", "claim": "x"}
    assert export.export_record(record, "masked") == record


def test_publication_check_ignores_full() -> None:
    assert export.publication_problems({}, [{"note": QUOTE}], [RECORD], "full") == []


@pytest.mark.parametrize("field", ["note", "justification"])
def test_check_catches_quote_in_other_record(path: str, field: str) -> None:
    add(path)
    add(path, quote=OTHER, **{field: QUOTE})
    with pytest.raises(ValueError, match=r"R-0002: contains source text from R-0001"):
        export.export_ledger(path, out_of(path), "masked")
    assert not Path(out_of(path)).exists()


def test_check_catches_changed_case_and_punctuation(path: str) -> None:
    add(path)
    add(path, quote=OTHER, note="“" + QUOTE.upper().replace(" ", " -- ") + "”!")
    with pytest.raises(ValueError, match="R-0002"):
        export.export_ledger(path, out_of(path), "locator")


def test_check_catches_prefix_in_note(path: str) -> None:
    add(path, note=f"Context: {PREFIX}")
    with pytest.raises(ValueError, match="R-0001: contains source text from R-0001"):
        export.export_ledger(path, out_of(path), "locator")


def test_check_catches_header_notes(tmp_path: Path) -> None:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK, notes=f"See: {QUOTE}")
    add(target)
    with pytest.raises(ValueError, match="header: contains source text from R-0001"):
        export.export_ledger(target, out_of(target), "masked")


def test_short_prefix_is_ignored(path: str) -> None:
    add(path, quote_prefix="In 2020,", note="In 2020, things changed.")
    result = export.export_ledger(path, out_of(path), "locator")
    assert result["records"] == 1


@pytest.mark.parametrize("level", ["masked", "locator"])
def test_clean_export_passes(path: str, level: str) -> None:
    add(path)
    add(path, quote=OTHER, note="Compare with the first record.")
    result = export.export_ledger(path, out_of(path), level)
    assert result == {"path": out_of(path), "level": level, "format": "jsonl", "records": 2}
    text = Path(out_of(path)).read_text("utf-8")
    lines = [json.loads(line) for line in text.splitlines()]
    assert lines[0]["ledger"]["work"] == WORK
    assert all("chunk" not in r["locator"] for r in lines[1:])
    assert QUOTE not in text


def test_json_format(path: str) -> None:
    add(path)
    export.export_ledger(path, out_of(path, "out.json"), "full", "json")
    doc = json.loads(Path(out_of(path, "out.json")).read_text("utf-8"))
    assert doc["ledger"]["work"] == WORK
    assert doc["records"][0]["quote"] == QUOTE


def test_existing_out_is_not_overwritten(path: str) -> None:
    add(path)
    target = Path(out_of(path))
    target.write_text("keep", "utf-8")
    with pytest.raises(FileExistsError):
        export.export_ledger(path, str(target))
    assert target.read_text("utf-8") == "keep"


def test_out_equal_to_path_is_refused(path: str) -> None:
    before = Path(path).read_bytes()
    with pytest.raises(ValueError, match="differ"):
        export.export_ledger(path, path)
    assert Path(path).read_bytes() == before


def test_withdrawn_records(path: str) -> None:
    add(path)
    add(path)
    ledger.withdraw_record(path, "R-0002", "Duplicate")
    assert export.export_ledger(path, out_of(path, "a.jsonl"))["records"] == 1
    result = export.export_ledger(path, out_of(path, "b.jsonl"), include_withdrawn=True)
    assert result["records"] == 2


def test_withdrawn_record_is_still_checked_as_source(path: str) -> None:
    add(path)
    ledger.withdraw_record(path, "R-0001", "Wrong source")
    add(path, quote=OTHER, note=QUOTE)
    with pytest.raises(ValueError, match="source text from R-0001"):
        export.export_ledger(path, out_of(path), "masked")


def test_invalid_level_and_format(path: str) -> None:
    with pytest.raises(ValueError, match="level"):
        export.export_ledger(path, out_of(path), "partial")
    with pytest.raises(ValueError, match="format"):
        export.export_ledger(path, out_of(path), format="csv")
