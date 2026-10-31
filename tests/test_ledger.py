from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import ledger
from evidence_ledger_mcp.schema import schema_version

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
RECORD: dict[str, Any] = {
    "claim": "Ledgers cut unchecked citations.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "cut unchecked citations"},
    "key": "exampleStudy2026",
    "no_identifier_reason": "Invented source for this test",
    "locator": {"page": 4},
    "quote": "Ledger records reduced unchecked citations from 40 to 3 per manuscript",
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}
README_HASH = "sha256-n2:3b8d67a25018dccc865ee88b24c10aa4a5b553e41ff28ebc46936a71eee7db3c"


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    return target


def add(path: str, **changes: Any) -> dict[str, Any]:
    return ledger.add_record(path, {**RECORD, **changes}, PROVENANCE)


def rewrite_line(path: str, index: int, record: dict[str, Any]) -> None:
    lines = Path(path).read_text("utf-8").splitlines()
    lines[index] = json.dumps(record)
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")


def test_quote_hash_normalizes() -> None:
    assert ledger.quote_hash(RECORD["quote"]) == README_HASH
    assert ledger.quote_hash(RECORD["quote"], "n1") == README_HASH.replace("n2:", "n1:")
    messy = "  LEDGER  records, reduced... unchecked citations from 40 to 3 per manuscript!"
    assert ledger.quote_hash(messy) == README_HASH
    assert ledger.quote_hash("ﬁx it") == ledger.quote_hash("FIX-IT")


def test_create_ledger_header_and_refusal(tmp_path: Path) -> None:
    target = str(tmp_path / "new.jsonl")
    header = ledger.create_ledger(target, WORK, description="d", notes="n")
    assert header["schema_version"] == schema_version()
    assert header["description"] == "d"
    assert json.loads(Path(target).read_text("utf-8")) == {"ledger": header}
    with pytest.raises(FileExistsError):
        ledger.create_ledger(target, WORK)
    with pytest.raises(ValueError, match="Invalid header"):
        ledger.create_ledger(str(tmp_path / "bad.jsonl"), {"title": "No type"})
    assert not (tmp_path / "bad.jsonl").exists()


def test_add_record_assigns_ids(path: str) -> None:
    first = add(path)
    second = add(path, key="other")
    shared = add(path, claim_id=first["claim_id"], quote_hash="sha256-n1:wrong")
    assert (first["id"], first["claim_id"]) == ("R-0001", "C-0001")
    assert (second["id"], second["claim_id"]) == ("R-0002", "C-0002")
    assert (shared["id"], shared["claim_id"]) == ("R-0003", "C-0001")
    assert shared["quote_hash"] == README_HASH
    assert first["provenance"]["date"]


def test_ids_count_withdrawn_records(path: str) -> None:
    add(path)
    ledger.withdraw_record(path, "R-0001", "Duplicate")
    assert add(path)["id"] == "R-0002"


def test_add_record_rejections_write_nothing(path: str) -> None:
    before = Path(path).read_text("utf-8")
    with pytest.raises(ValueError, match="'id'"):
        add(path, id="R-0099")
    with pytest.raises(ValueError, match="'withdrawn'"):
        add(path, withdrawn="x")
    with pytest.raises(ValueError, match="Invalid record"):
        add(path, claim_type="nonsense")
    assert Path(path).read_text("utf-8") == before


def test_get_record(path: str) -> None:
    add(path)
    assert ledger.get_record(path, "R-0001")["key"] == RECORD["key"]
    with pytest.raises(ValueError, match="R-0009"):
        ledger.get_record(path, "R-0009")


def test_find_records_filters(path: str) -> None:
    add(path)
    add(path, key="other", claim="Something ELSE entirely.")
    add(path, claim_id="C-0001")
    ledger.withdraw_record(path, "R-0003", "Duplicate")

    def ids(**filters: Any) -> list[str]:
        return [r["id"] for r in ledger.find_records(path, **filters)]

    assert ids() == ["R-0001", "R-0002"]
    assert ids(include_withdrawn=True) == ["R-0001", "R-0002", "R-0003"]
    assert ids(claim_id="C-0001") == ["R-0001"]
    assert ids(key="other") == ["R-0002"]
    assert ids(text="else ENTIRELY") == ["R-0002"]
    assert ids(key="other", text="ledgers") == []
    assert ids(missing_evidence=True) == []


def test_find_missing_evidence_from_hand_edit(path: str) -> None:
    bare = {k: v for k, v in add(path).items() if k not in ledger.EVIDENCE_FIELDS}
    rewrite_line(path, 1, bare)
    assert [r["id"] for r in ledger.find_records(path, missing_evidence=True)] == ["R-0001"]


def test_find_missing_evidence_when_one_field_lacks(path: str) -> None:
    partial = {k: v for k, v in add(path).items() if k != "justification"}
    rewrite_line(path, 1, partial)
    assert [r["id"] for r in ledger.find_records(path, missing_evidence=True)] == ["R-0001"]


def test_withdraw_record(path: str) -> None:
    add(path)
    add(path)
    withdrawn = ledger.withdraw_record(path, "R-0001", "Duplicate")
    assert withdrawn["withdrawn"] == "Duplicate"
    lines = Path(path).read_text("utf-8").splitlines()
    assert len(lines) == 3
    assert json.loads(lines[1])["withdrawn"] == "Duplicate"
    assert "withdrawn" not in json.loads(lines[2])
    with pytest.raises(ValueError, match="already withdrawn"):
        ledger.withdraw_record(path, "R-0001", "Again")
    with pytest.raises(ValueError, match="R-0009"):
        ledger.withdraw_record(path, "R-0009", "Unknown")


def test_validate_clean_ledger(path: str) -> None:
    add(path)
    assert ledger.validate_ledger(path) == []


def test_validate_reports_each_problem(path: str) -> None:
    first = add(path)
    second = add(path, claim_id="C-0001")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write(json.dumps({**second, "id": "R-0009", "importance": "critical"}) + "\n")
        handle.write(json.dumps({**first, "claim_type": "nonsense", "quote": "Changed"}) + "\n")
    lines = Path(path).read_text("utf-8").splitlines()
    header = {"ledger": {**json.loads(lines[0])["ledger"], "schema_version": "0.0.1"}}
    lines[0] = json.dumps(header)
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")
    problems = "\n".join(ledger.validate_ledger(path))
    assert "schema_version 0.0.1 differs" in problems
    assert "line 4: not valid JSON" in problems
    assert "R-0001: claim_type" in problems
    assert "R-0001: duplicate id" in problems
    assert "R-0001: quote_hash does not match quote" in problems
    assert "C-0001: records disagree on importance" in problems


def test_validate_reports_bad_header(path: str) -> None:
    Path(path).write_text(json.dumps({"ledger": {"schema_version": "x"}}) + "\n", "utf-8")
    assert any(p.startswith("header:") for p in ledger.validate_ledger(path))


def test_line_separators_inside_fields_stay_on_one_line(path: str) -> None:
    add(path, quote="a\u2028b\u0085c")
    add(path)
    assert [r["id"] for r in ledger.find_records(path)] == ["R-0001", "R-0002"]
    assert ledger.validate_ledger(path) == []


def test_append_after_missing_final_newline(path: str) -> None:
    add(path)
    Path(path).write_bytes(Path(path).read_bytes().rstrip(b"\n"))
    add(path)
    assert ledger.validate_ledger(path) == []


def test_add_record_refuses_what_validation_flags(path: str) -> None:
    add(path, importance="critical")
    with pytest.raises(ValueError, match="importance differs"):
        add(path, claim_id="C-0001", importance="supporting")
    with pytest.raises(ValueError, match="without 'quote'"):
        ledger.add_record(path, {"quote_hash": README_HASH}, PROVENANCE)
    stored = ledger.add_record(
        path,
        {**RECORD, "claim_id": "C-0001", "importance": "critical"},
        {**PROVENANCE, "date": "1999-01-01"},
    )
    assert stored["provenance"]["date"] != "1999-01-01"
    assert ledger.validate_ledger(path) == []


def test_header_with_bom_is_read(path: str) -> None:
    Path(path).write_bytes(b"\xef\xbb\xbf" + Path(path).read_bytes())
    assert add(path)["id"] == "R-0001"


def test_validate_reports_unhashable_importance(path: str) -> None:
    rewrite_line(path, 1, {**add(path), "importance": ["critical"]})
    assert any(p.startswith("R-0001: importance") for p in ledger.validate_ledger(path))


@pytest.mark.parametrize("quote", ["ΐ", "\u0399\u0308\u0301", "ǰ", "J̌", "ẖ", "H̱"])
def test_n2_case_stable(quote: str) -> None:
    assert ledger.quote_hash(quote) == ledger.quote_hash(quote.upper())


def test_greek_hash_vector() -> None:
    assert ledger.normalize("ΐ") == "ΐ"
    assert (
        ledger.quote_hash("ΐ")
        == "sha256-n2:e45728ad6aeb8fcc4a0b4669abd3eed0b5e6aea36feae65b0ab69ce5ade3ac2d"
    )


def test_legacy_hash_is_checked(path: str) -> None:
    record = add(path, quote="ΐ")
    record["quote_hash"] = ledger.quote_hash("ΐ", "n1")
    assert record["quote_hash"] != ledger.quote_hash("ΐ")
    rewrite_line(path, 1, record)
    assert ledger.validate_ledger(path) == []
    record["quote_hash"] = "sha256-n9:" + "0" * 64
    rewrite_line(path, 1, record)
    assert any("quote_hash" in e for e in ledger.validate_ledger(path))


@pytest.mark.parametrize("focus", ["missing", "cit", " citations", " ", "Ledger Ledger"])
def test_bad_focus_writes_nothing(path: str, focus: str) -> None:
    before = Path(path).read_bytes()
    with pytest.raises(ValueError, match="quote_focus"):
        add(path, quote_focus=focus)
    assert Path(path).read_bytes() == before


def test_duplicate_and_oversized_focus(path: str) -> None:
    for quote, focus in [
        ("word word", "word"),
        (" ".join(map(str, range(26))), " ".join(map(str, range(26)))),
    ]:
        with pytest.raises(ValueError, match="quote_focus"):
            add(path, quote=quote, quote_focus=focus)


def test_focus_hand_edit_is_validated(path: str) -> None:
    record = add(path, quote_focus="40 to 3")
    record["quote_focus"] = "missing"
    rewrite_line(path, 1, record)
    assert any("quote_focus" in e for e in ledger.validate_ledger(path))


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        (
            {"justification": "It says reduced unchecked citations from 40 to 3 per manuscript."},
            "justification",
        ),
        (
            {"locator": {"section": "Ledger records reduced unchecked citations from 40"}},
            "locator.section",
        ),
        ({"note": "reduced unchecked citations from 40 to 3"}, "note"),
    ],
)
def test_add_record_refuses_source_text_outside_quote_fields(
    path: str, changes: dict[str, Any], field: str
) -> None:
    with pytest.raises(ValueError, match=f"{field} repeats source text"):
        add(path, **changes)
    assert ledger.read(path)[1] == []


def test_add_record_allows_short_shared_wording_and_the_work_fields(path: str) -> None:
    stored = add(
        path,
        justification="Counts of unchecked citations fell.",
        claim="Ledger records reduced unchecked citations from 40 to 3 per manuscript",
        anchor={"exact": "Ledger records reduced unchecked citations from 40 to 3"},
    )
    assert stored["id"] == "R-0001"


def test_server_tells_agents_where_source_text_goes() -> None:
    from evidence_ledger_mcp import server

    assert "quote_focus" in (server.mcp.instructions or "")
    assert "own words" in (server.mcp.instructions or "")


def test_add_record_checks_header_fields(tmp_path: Path) -> None:
    target = str(tmp_path / "h.jsonl")
    ledger.create_ledger(target, WORK, description="Covers: " + RECORD["quote"])
    with pytest.raises(ValueError, match=r"header\.description"):
        ledger.add_record(target, RECORD, PROVENANCE)


def test_prefix_suffix_focus_and_provenance_count_as_source(path: str) -> None:
    prefix = "In the second year of the trial,"
    suffix = "which held across every later replication"
    with pytest.raises(ValueError, match="note repeats source text"):
        add(path, quote_prefix=prefix, note=f"Context: {prefix}")
    with pytest.raises(ValueError, match="note repeats source text"):
        add(path, quote_suffix=suffix, note=suffix)
    focus = "reduced unchecked citations from 40 to 3"
    with pytest.raises(ValueError, match="justification repeats"):
        add(path, quote_focus=focus, justification=f"Reads {focus}.")
    with pytest.raises(ValueError, match=r"provenance\.by repeats"):
        ledger.add_record(path, RECORD, {**PROVENANCE, "by": RECORD["quote"]})


def test_window_boundary_is_24_letters_and_digits(path: str) -> None:
    run = "abcdefghijklmnopqrstuvwx"
    assert len(run) == ledger.WINDOW == 24
    add(path, quote=f"Start {run} end", note=run[:23])
    with pytest.raises(ValueError, match="note repeats source text"):
        add(path, quote=f"Start {run} end", note=run)


def test_validate_ledger_reports_source_overlaps(path: str) -> None:
    add(path)
    lines = Path(path).read_text("utf-8").splitlines()
    lines[-1] = json.dumps({**json.loads(lines[-1]), "note": RECORD["quote"]})
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")
    problems = ledger.validate_ledger(path)
    assert any(p.startswith("R-0001: note repeats source text") for p in problems)
