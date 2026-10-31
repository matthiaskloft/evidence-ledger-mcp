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


def add_with_note(path: str, note: str) -> None:
    """Add a record, then put a note on it by hand: add_record refuses such notes."""
    add(path)
    lines = Path(path).read_text("utf-8").splitlines()
    lines[-1] = json.dumps({**json.loads(lines[-1]), "note": note})
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")


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
    add_with_note(path, f"Context: {PREFIX}")
    with pytest.raises(ValueError, match="R-0001: contains source text from R-0001"):
        export.export_ledger(path, out_of(path), "locator")


def test_check_catches_header_notes(tmp_path: Path) -> None:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    add(target)
    lines = Path(target).read_text("utf-8").splitlines()
    header = json.loads(lines[0])
    header["ledger"]["notes"] = f"See: {QUOTE}"
    lines[0] = json.dumps(header)
    Path(target).write_text("\n".join(lines) + "\n", "utf-8")
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


def test_check_catches_part_of_a_quote(path: str) -> None:
    add(path)
    add(path, quote=OTHER, note=" ".join(QUOTE.split()[2:-2]))
    with pytest.raises(ValueError, match="R-0002"):
        export.export_ledger(path, out_of(path), "locator")


def test_check_catches_unspaced_script(path: str) -> None:
    quote = "台帳の記録は原稿あたりの未確認の引用を四十件から三件に減らした"
    add(path, quote=quote)
    add(path, quote=OTHER, note=quote)
    with pytest.raises(ValueError, match="R-0002"):
        export.export_ledger(path, out_of(path), "locator")


def test_stock_prefix_in_prose_passes(path: str) -> None:
    add(path, quote_prefix="As shown in Table 2,")
    add(path, quote=OTHER, note="As shown in Table 2, our sample differs.")
    assert export.export_ledger(path, out_of(path), "locator")["records"] == 2


def test_claim_may_echo_its_quote(path: str) -> None:
    add(path, claim=f"Studies report that {QUOTE}.", anchor={"exact": QUOTE})
    assert export.export_ledger(path, out_of(path), "masked")["records"] == 1


@pytest.mark.parametrize(
    ("quote", "budget", "expected"),
    [
        ("one two", 3, "one two"),
        ("one two", 2, "one two"),
        ("one two three four five six", 4, "one two … five six"),
        ("one two three four five six", 3, "one two … six"),
        ("one two three", 1, "one …"),
        ("one\ttwo\nthree four", 2, "one … four"),
    ],
)
def test_budget_mask(quote: str, budget: int, expected: str) -> None:
    assert export.mask_quote(quote, budget) == expected


@pytest.mark.parametrize("level", ["full", "locator"])
def test_budget_requires_masked(path: str, level: str) -> None:
    with pytest.raises(ValueError, match="only allowed"):
        export.export_ledger(path, out_of(path), level, max_words=4)
    assert not Path(out_of(path)).exists()


@pytest.mark.parametrize("budget", [0, -1, export.MAX_EXCERPT_WORDS + 1, True, 1.5])
def test_invalid_budget(path: str, budget: Any) -> None:
    with pytest.raises(ValueError, match=str(export.MAX_EXCERPT_WORDS)):
        export.export_ledger(path, out_of(path), "masked", max_words=budget)
    assert not Path(out_of(path)).exists()


@pytest.mark.parametrize("fmt", ["json", "jsonl"])
@pytest.mark.parametrize("budget", [None, 4, export.MAX_EXCERPT_WORDS])
def test_budget_export_header(path: str, fmt: str, budget: int | None) -> None:
    add(path)
    export.export_ledger(path, out_of(path), "masked", fmt, max_words=budget)
    text = Path(out_of(path)).read_text("utf-8")
    doc = (
        json.loads(text)
        if fmt == "json"
        else {
            "ledger": json.loads(text.splitlines()[0])["ledger"],
            "records": [json.loads(text.splitlines()[1])],
        }
    )
    assert doc["ledger"]["level"] == "masked"
    assert doc["ledger"]["max_words"] == budget
    assert doc["records"][0]["quote"] == export.mask_quote(QUOTE, budget)


@pytest.mark.parametrize("budget", [None, 4])
def test_check_distrusts_masker(
    path: str, monkeypatch: pytest.MonkeyPatch, budget: int | None
) -> None:
    add(path)
    monkeypatch.setattr(export, "mask_quote", lambda quote, max_words=None: quote)
    with pytest.raises(ValueError, match="masked quote"):
        export.export_ledger(path, out_of(path), "masked", max_words=budget)
    assert not Path(out_of(path)).exists()


@pytest.mark.parametrize("masked", ["manuscript … Ledger", "invented words", "Ledger … Ledger"])
def test_check_requires_ordered_source_parts(masked: str) -> None:
    original = {"id": "R-0001", "quote": QUOTE}
    assert export.publication_problems(
        {}, [{"id": "R-0001", "quote": masked}], [original], "masked", 4
    )


@pytest.mark.parametrize(
    ("focus", "expected"),
    [
        ("a", "a b c d …"),
        ("e f", "… d e f g …"),
        ("j", "… g h i j"),
    ],
)
def test_focus_window(focus: str, expected: str) -> None:
    assert export.mask_quote("a b c d e f g h i j", 4, focus) == expected


def test_short_focus_quote_and_budget_error() -> None:
    assert export.mask_quote("a b c", 5, "b") == "a b c"
    with pytest.raises(ValueError, match="longer than max_words"):
        export.mask_quote("a b c d", 1, "b c")


@pytest.mark.parametrize("level", ["masked", "locator"])
@pytest.mark.parametrize("budget", [None, 5])
def test_focus_removed_from_export(path: str, level: str, budget: int | None) -> None:
    if level == "locator" and budget is not None:
        return
    add(path, quote_focus="40 to 3")
    export.export_ledger(path, out_of(path), level, max_words=budget)
    record = json.loads(Path(out_of(path)).read_text("utf-8").splitlines()[1])
    assert "quote_focus" not in record
    if level == "masked":
        expected = "… from 40 to 3 per …" if budget else "Ledger records … per manuscript"
        assert record["quote"] == expected


def test_full_retains_focus(path: str) -> None:
    add(path, quote_focus="40 to 3")
    export.export_ledger(path, out_of(path))
    record = json.loads(Path(out_of(path)).read_text("utf-8").splitlines()[1])
    assert record["quote_focus"] == "40 to 3"


def test_focus_budget_error_writes_nothing(path: str) -> None:
    add(path, quote_focus="40 to 3")
    with pytest.raises(ValueError, match="longer than max_words"):
        export.export_ledger(path, out_of(path), "masked", max_words=2)
    assert not Path(out_of(path)).exists()


@pytest.mark.parametrize("quote", ["one…two three", "one … two three"])
def test_literal_ellipsis_in_budget_export(path: str, quote: str) -> None:
    add(path, quote=quote)
    export.export_ledger(path, out_of(path), "masked", max_words=5)
    record = json.loads(Path(out_of(path)).read_text("utf-8").splitlines()[1])
    assert record["quote"] == quote


def test_full_export_remains_a_valid_ledger(path: str) -> None:
    add(path)
    export.export_ledger(path, out_of(path))
    assert ledger.validate_ledger(out_of(path)) == []


@pytest.mark.parametrize(
    ("level", "max_words"), [("masked", None), ("masked", 5), ("locator", None)]
)
def test_masked_and_locator_exports_remain_valid_ledgers(
    path: str, level: str, max_words: int | None
) -> None:
    add(path, quote_focus="reduced unchecked citations")
    export.export_ledger(path, out_of(path), level, max_words=max_words)
    assert ledger.validate_ledger(out_of(path)) == []


def edit_export(path: str, level: str, **changes: Any) -> list[str]:
    add(path)
    export.export_ledger(path, out_of(path), level)
    out = Path(out_of(path))
    head, body = out.read_text("utf-8").splitlines()
    record = {**json.loads(body), **changes}
    out.write_text(head + "\n" + json.dumps(record) + "\n", "utf-8")
    return ledger.validate_ledger(str(out))


def test_locator_export_with_source_text_is_invalid(path: str) -> None:
    problems = edit_export(path, "locator", quote=QUOTE)
    assert "R-0001: locator export contains quote" in problems


def test_masked_export_with_longer_quote_and_context_is_invalid(path: str) -> None:
    problems = edit_export(path, "masked", quote=QUOTE, quote_prefix=PREFIX)
    assert any("masked quote exceeds its budget" in p for p in problems)
    assert "R-0001: masked export contains quote_prefix" in problems


def test_locator_export_still_reports_genuine_problems(path: str) -> None:
    problems = edit_export(path, "locator", quote_hash="sha256-n2:nothex")
    assert any("quote_hash" in p for p in problems)


def test_masked_export_with_inflated_max_words_is_invalid(path: str) -> None:
    add(path)
    export.export_ledger(path, out_of(path), "masked")
    out = Path(out_of(path))
    head, body = out.read_text("utf-8").splitlines()
    header = json.loads(head)
    header["ledger"]["max_words"] = 1000
    record = {**json.loads(body), "quote": QUOTE}
    out.write_text(json.dumps(header) + "\n" + json.dumps(record) + "\n", "utf-8")
    problems = ledger.validate_ledger(str(out))
    assert any("masked quote exceeds its budget" in p for p in problems)
    assert any("max_words must be an integer from 1 to" in p for p in problems)
