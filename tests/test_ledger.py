from __future__ import annotations

import json
import os
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


def test_validate_ledger_reports_header_overlaps(path: str) -> None:
    add(path)
    lines = Path(path).read_text("utf-8").splitlines()
    first = json.loads(lines[0])
    first["ledger"]["notes"] = "Covers: " + RECORD["quote"]
    lines[0] = json.dumps(first)
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")
    assert "R-0001: header.notes repeats source text" in ledger.validate_ledger(path)


def update(path: str, record_id: str, **changes: Any) -> dict[str, Any]:
    return ledger.update_record(path, record_id, changes)


def test_update_record_merges_and_keeps_provenance(path: str) -> None:
    original = add(path, note="Old note")["provenance"]
    add(path, key="other")
    other_line = Path(path).read_text("utf-8").splitlines()[2]
    stored = update(path, "R-0001", locator={"page": 9}, note=None)
    assert stored["locator"] == {"page": 9}
    assert "note" not in stored
    assert (stored["id"], stored["claim_id"]) == ("R-0001", "C-0001")
    assert stored["provenance"] == original
    assert ledger.get_record(path, "R-0001") == stored
    assert Path(path).read_text("utf-8").splitlines()[2] == other_line
    assert ledger.validate_ledger(path) == []


def test_update_record_does_not_touch_an_old_provenance_date(path: str) -> None:
    old = {**PROVENANCE, "date": "2020-01-02", "manuscript_rev": "v1"}
    add(path)
    rewrite_line(path, 1, {**ledger.read(path)[1][0], "provenance": old})
    stored = update(path, "R-0001", note="Edited")
    assert stored["provenance"] == old


def test_update_record_quote_hash(path: str) -> None:
    kept = add(path)
    legacy = {**kept, "quote_hash": ledger.quote_hash(kept["quote"], "n1")}
    rewrite_line(path, 1, legacy)
    unchanged = update(path, "R-0001", quote=kept["quote"], justification="Reworded.")
    assert unchanged["quote_hash"].startswith("sha256-n1:")
    new_quote = "Ledger records reduced unchecked citations from 40 to 2 per manuscript"
    changed = update(path, "R-0001", quote=new_quote)
    assert changed["quote_hash"] == ledger.quote_hash(new_quote)
    assert changed["quote_hash"].startswith("sha256-n2:")
    assert ledger.validate_ledger(path) == []
    removed = update(
        path,
        "R-0001",
        quote=None,
        justification=None,
        locator=None,
        contestable=False,
        contestable_reason="Common knowledge",
    )
    assert "quote" not in removed
    assert "quote_hash" not in removed


def test_update_record_copies_claim_fields_to_the_claim(path: str) -> None:
    add(path, importance="critical")
    add(path, claim_id="C-0001", key="other", importance="critical")
    add(path, claim_id="C-0001", key="third", importance="critical")
    add(path, key="elsewhere", claim="Another claim.")
    ledger.withdraw_record(path, "R-0003", "Duplicate")
    before = {r["id"]: r for r in ledger.read(path)[1]}
    update(path, "R-0001", claim="Ledgers cut unchecked citations a lot.", importance="supporting")
    after = {r["id"]: r for r in ledger.read(path)[1]}
    for id in ("R-0001", "R-0002", "R-0003"):
        assert after[id]["claim"] == "Ledgers cut unchecked citations a lot."
        assert after[id]["importance"] == "supporting"
    for id in ("R-0002", "R-0003"):
        assert after[id]["provenance"] == before[id]["provenance"]
    assert after["R-0003"]["withdrawn"] == "Duplicate"
    assert after["R-0004"] == before["R-0004"]
    assert ledger.validate_ledger(path) == []
    update(path, "R-0002", importance=None)
    assert all("importance" not in r for r in ledger.read(path)[1][:3])
    assert ledger.validate_ledger(path) == []


def test_update_record_non_claim_change_leaves_siblings(path: str) -> None:
    add(path)
    add(path, claim_id="C-0001", key="other")
    before = Path(path).read_text("utf-8").splitlines()[2]
    update(path, "R-0001", key="changed")
    assert Path(path).read_text("utf-8").splitlines()[2] == before


@pytest.mark.parametrize(
    ("id", "changes", "match"),
    [
        ("R-0001", {"id": "R-0009"}, "'id'"),
        ("R-0001", {"withdrawn": "x"}, "'withdrawn'"),
        ("R-0001", {"quote_hash": README_HASH}, "'quote_hash'"),
        ("R-0001", {"provenance": {"by_type": "agent", "by": "X"}}, "'provenance'"),
        ("R-0001", {}, "No changes"),
        ("R-0009", {"note": "x"}, "R-0009"),
        ("R-0003", {"note": "x"}, "withdrawn"),
        ("R-0001", {"claim_type": "nonsense"}, "Invalid record"),
        ("R-0001", {"quote_focus": "missing"}, "quote_focus"),
        (
            "R-0001",
            {"justification": "Reduced unchecked citations from 40 to 3 per manuscript."},
            "justification repeats source text",
        ),
        ("R-0001", {"claim_id": "C-0002"}, "claim differs from R-0002 on C-0002"),
        ("R-0001", {"claim_id": "C-0002", "claim": "Another claim."}, "importance differs"),
    ],
)
def test_update_record_rejections_write_nothing(
    path: str, id: str, changes: dict[str, Any], match: str
) -> None:
    add(path)
    add(path, key="other", claim="Another claim.", importance="critical")
    add(path)
    ledger.withdraw_record(path, "R-0003", "Duplicate")
    before = Path(path).read_bytes()
    with pytest.raises(ValueError, match=match):
        ledger.update_record(path, id, changes)
    assert Path(path).read_bytes() == before


def test_update_records_applies_twenty_anchor_edits_at_once(path: str) -> None:
    for number in range(20):
        add(path, key=f"s{number}", claim=f"Claim {number}.", anchor={"exact": f"old {number}"})
    before = ledger.read(path)[1]
    updates = [
        {"id": f"R-{n + 1:04d}", "changes": {"anchor": {"exact": f"new {n}"}}} for n in range(20)
    ]
    stored = ledger.update_records(path, updates)
    assert [r["anchor"]["exact"] for r in stored] == [f"new {n}" for n in range(20)]
    after = ledger.read(path)[1]
    assert [r["anchor"]["exact"] for r in after] == [f"new {n}" for n in range(20)]
    assert [r["provenance"] for r in after] == [r["provenance"] for r in before]
    assert ledger.validate_ledger(path) == []


def test_update_records_reports_every_refusal_and_writes_nothing(path: str) -> None:
    add(path)
    add(path, key="other", claim="Another claim.")
    before = Path(path).read_bytes()
    updates = [
        {"id": "R-0001", "changes": {"note": "fine"}},
        {"id": "R-0002", "changes": {"claim_type": "nonsense"}},
        {"id": "R-0009", "changes": {"note": "x"}},
    ]
    with pytest.raises(ValueError) as error:
        ledger.update_records(path, updates)
    message = str(error.value)
    assert "updates[1] (R-0002): Invalid record" in message
    assert "updates[2] (R-0009): No record R-0009" in message
    assert "updates[0]" not in message
    assert Path(path).read_bytes() == before


def test_update_records_apply_in_order(path: str) -> None:
    add(path)
    stored = ledger.update_records(
        path,
        [
            {"id": "R-0001", "changes": {"note": "first"}},
            {"id": "R-0001", "changes": {"note": "second", "locator": {"page": 4}}},
        ],
    )
    assert [r["note"] for r in stored] == ["second", "second"]
    assert ledger.get_record(path, "R-0001")["locator"] == {"page": 4}
    # Order matters: the last update to a field wins.
    ledger.update_records(
        path,
        [
            {"id": "R-0001", "changes": {"note": None}},
            {"id": "R-0001", "changes": {"note": "back"}},
        ],
    )
    assert ledger.get_record(path, "R-0001")["note"] == "back"
    ledger.update_records(
        path,
        [
            {"id": "R-0001", "changes": {"note": "x"}},
            {"id": "R-0001", "changes": {"note": None}},
        ],
    )
    assert "note" not in ledger.get_record(path, "R-0001")


def test_update_records_propagate_claim_changes_within_a_batch(path: str) -> None:
    add(path)
    add(path, claim_id="C-0001", key="other")
    ledger.update_records(
        path,
        [
            {"id": "R-0001", "changes": {"claim": "Reworded claim."}},
            {"id": "R-0002", "changes": {"note": "sees the new claim"}},
        ],
    )
    claims = {r["id"]: r["claim"] for r in ledger.read(path)[1]}
    assert claims == {"R-0001": "Reworded claim.", "R-0002": "Reworded claim."}
    # A later claim edit on a sibling in the same batch wins for the whole claim.
    ledger.update_records(
        path,
        [
            {"id": "R-0001", "changes": {"claim": "One."}},
            {"id": "R-0002", "changes": {"claim": "Two."}},
        ],
    )
    assert {r["claim"] for r in ledger.read(path)[1]} == {"Two."}
    assert ledger.validate_ledger(path) == []


def test_update_record_checks_header_overlap(tmp_path: Path) -> None:
    target = str(tmp_path / "h.jsonl")
    ledger.create_ledger(target, WORK, description="Covers: " + RECORD["quote"])
    line = json.dumps(
        RECORD
        | {
            "id": "R-0001",
            "claim_id": "C-0001",
            "quote_hash": README_HASH,
            "provenance": {**PROVENANCE, "date": "2026-01-01"},
        }
    )
    Path(target).write_text(Path(target).read_text("utf-8") + line + "\n", "utf-8")
    before = Path(target).read_bytes()
    with pytest.raises(ValueError, match=r"header\.description"):
        update(target, "R-0001", note="x")
    assert Path(target).read_bytes() == before


def test_update_record_fixes_a_hand_edited_disagreement(path: str) -> None:
    add(path)
    add(path, claim_id="C-0001", key="other")
    rewrite_line(path, 2, {**ledger.read(path)[1][1], "claim": "Drifted."})
    assert "C-0001: records disagree on claim text" in ledger.validate_ledger(path)
    update(path, "R-0001", claim="Agreed wording.")
    assert ledger.validate_ledger(path) == []


def test_add_record_refuses_a_different_claim_text(path: str) -> None:
    add(path)
    before = Path(path).read_bytes()
    with pytest.raises(ValueError, match="claim differs from R-0001 on C-0001"):
        add(path, claim_id="C-0001", claim="A different claim.")
    assert Path(path).read_bytes() == before


def test_validate_reports_claim_text_disagreement(path: str) -> None:
    add(path)
    second = add(path, claim_id="C-0001")
    rewrite_line(path, 2, {**second, "claim": "A different claim."})
    assert "C-0001: records disagree on claim text" in ledger.validate_ledger(path)


@pytest.fixture
def pair(tmp_path: Path) -> tuple[str, str]:
    first, second = str(tmp_path / "schema.jsonl"), str(tmp_path / "server.jsonl")
    ledger.create_ledger(first, WORK)
    ledger.create_ledger(second, WORK)
    return first, second


def add_related(path: str, related: list[str], **changes: Any) -> dict[str, Any]:
    return ledger.add_record(path, {**RECORD, **changes}, PROVENANCE, related)


def snapshot(*paths: str) -> list[bytes]:
    return [Path(p).read_bytes() for p in paths]


def test_add_record_numbers_past_related_ledgers(pair: tuple[str, str]) -> None:
    first, second = pair
    added = [
        add_related(first, [second]),
        add_related(second, [first], claim="Second claim."),
        add_related(first, [second], claim="Third claim."),
        add_related(second, [first], claim="Fourth claim."),
    ]
    assert [r["id"] for r in added] == ["R-0001", "R-0002", "R-0003", "R-0004"]
    assert [r["claim_id"] for r in added] == ["C-0001", "C-0002", "C-0003", "C-0004"]
    assert ledger.validate_ledger(first, [second]) == []
    assert ledger.validate_ledger(second, [first, second]) == []


def test_add_record_without_related_numbers_per_ledger(pair: tuple[str, str]) -> None:
    first, second = pair
    add(first)
    assert add(second)["id"] == "R-0001"


def test_move_record_keeps_everything_and_never_reuses_the_id(pair: tuple[str, str]) -> None:
    first, second = pair
    add_related(first, [second])
    add_related(first, [second], claim="Moved claim.")
    ledger.withdraw_record(first, "R-0002", "Not needed")
    stored = ledger.get_record(first, "R-0002")
    assert ledger.move_record(first, "R-0002", second) == stored
    assert [r["id"] for r in ledger.read(first)[1]] == ["R-0001"]
    assert ledger.read(second)[1] == [stored]
    assert ledger.validate_ledger(first, [second]) == []
    assert ledger.validate_ledger(second, [first]) == []
    assert add_related(first, [second], claim="Later.")["id"] == "R-0003"


def test_move_record_refusals_write_nothing(pair: tuple[str, str]) -> None:
    first, second = pair
    add_related(first, [second])
    add_related(second, [first], claim="Other.")
    rewrite_line(second, 1, {**ledger.read(second)[1][0], "id": "R-0001"})
    before = snapshot(first, second)
    for args, match in [
        ((first, "R-0001", first), "same ledger"),
        ((first, "R-0009", second), "No record R-0009"),
        ((first, "R-0001", second), "already exists"),
    ]:
        with pytest.raises(ValueError, match=match):
            ledger.move_record(*args)
        assert snapshot(first, second) == before


def test_move_record_runs_the_target_checks(pair: tuple[str, str]) -> None:
    first, second = pair
    add_related(first, [second])
    rewrite_line(second, 0, {"ledger": {**ledger.read(second)[0], "notes": RECORD["quote"]}})
    before = snapshot(first, second)
    with pytest.raises(ValueError, match=r"header\.notes"):
        ledger.move_record(first, "R-0001", second)
    assert snapshot(first, second) == before


def test_move_record_refuses_a_claim_disagreement(pair: tuple[str, str]) -> None:
    first, second = pair
    add_related(first, [second])
    other = {**ledger.read(first)[1][0], "id": "R-0002", "claim": "A different wording."}
    with open(second, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(other) + "\n")
    before = snapshot(first, second)
    with pytest.raises(ValueError, match="claim differs from R-0002 on C-0001"):
        ledger.move_record(first, "R-0001", second)
    assert snapshot(first, second) == before


def test_validate_ledger_reports_ids_shared_with_related(pair: tuple[str, str]) -> None:
    first, second = pair
    add_related(first, [second])
    with open(second, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(ledger.read(first)[1][0]) + "\n")
    assert ledger.validate_ledger(first) == []
    assert ledger.validate_ledger(first, [second]) == [f"R-0001: id also used in {second}"]
    assert ledger.validate_ledger(second, [first]) == [f"R-0001: id also used in {first}"]
    assert ledger.validate_ledger(first, [first]) == []


def split_claim(pair: tuple[str, str]) -> tuple[str, str]:
    """Two records on C-0001, one moved to the second ledger."""
    first, second = pair
    add_related(first, [second])
    add_related(first, [second], claim_id="C-0001")
    ledger.move_record(first, "R-0002", second)
    return first, second


def test_add_record_checks_claim_agreement_across_related(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    before = snapshot(first, second)
    for changes, match in [
        ({"claim": "A different wording."}, "claim differs from R-000. on C-0001"),
        ({"importance": "critical"}, "importance differs from R-000. on C-0001"),
    ]:
        with pytest.raises(ValueError, match=match):
            add_related(first, [second], claim_id="C-0001", **changes)
        assert snapshot(first, second) == before
    assert add_related(first, [second], claim_id="C-0001")["id"] == "R-0003"


def test_update_record_copies_claim_changes_to_related(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    old = ledger.get_record(second, "R-0002")["provenance"]
    ledger.update_record(first, "R-0001", {"claim": "New wording."}, [second])
    assert ledger.get_record(first, "R-0001")["claim"] == "New wording."
    other = ledger.get_record(second, "R-0002")
    assert other["claim"] == "New wording."
    assert other["provenance"] == old
    assert ledger.validate_ledger(first, [second]) == []
    assert ledger.validate_ledger(second, [first]) == []


def test_update_record_failing_check_writes_no_file(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    # The edited ledger's header repeats the quote, so the edited record fails.
    rewrite_line(first, 0, {"ledger": {**ledger.read(first)[0], "notes": RECORD["quote"]}})
    before = snapshot(first, second)
    with pytest.raises(ValueError, match=r"header\.notes"):
        ledger.update_record(first, "R-0001", {"claim": "New wording."}, [second])
    assert snapshot(first, second) == before
    # The related ledger's header makes the copied record fail there.
    rewrite_line(first, 0, {"ledger": ledger.read(first)[0] | {"notes": "Own words."}})
    rewrite_line(second, 0, {"ledger": {**ledger.read(second)[0], "notes": RECORD["quote"]}})
    before = snapshot(first, second)
    with pytest.raises(ValueError, match=r"header\.notes"):
        ledger.update_record(first, "R-0001", {"claim": "New wording."}, [second])
    assert snapshot(first, second) == before


def test_update_record_without_related_leaves_other_ledger(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    before = snapshot(second)
    ledger.update_record(first, "R-0001", {"claim": "New wording."})
    assert snapshot(second) == before
    assert ledger.validate_ledger(first) == []
    assert ledger.validate_ledger(second, [first]) == [
        "C-0001: records disagree on claim text across related ledgers"
    ]


def test_update_records_batch_propagates_claim_to_related(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    result = ledger.update_records(
        first, [{"id": "R-0001", "changes": {"claim": "New wording."}}], [second]
    )
    assert result[0]["claim"] == "New wording."
    assert ledger.get_record(second, "R-0002")["claim"] == "New wording."
    assert ledger.validate_ledger(first, [second]) == []


def test_update_records_bad_item_writes_neither_file(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    before = snapshot(first, second)
    with pytest.raises(ValueError, match=r"nothing written.*updates\[1\] \(R-0999\)"):
        ledger.update_records(
            first,
            [
                {"id": "R-0001", "changes": {"claim": "New wording."}},
                {"id": "R-0999", "changes": {"note": "x"}},
            ],
            [second],
        )
    assert snapshot(first, second) == before


def test_validate_reports_drift_across_related(pair: tuple[str, str]) -> None:
    first, second = split_claim(pair)
    rewrite_line(
        second, 1, {**ledger.read(second)[1][0], "claim": "Drifted.", "importance": "critical"}
    )
    assert ledger.validate_ledger(second) == []
    assert ledger.validate_ledger(first, [second]) == [
        "C-0001: records disagree on claim text across related ledgers",
        "C-0001: records disagree on importance across related ledgers",
    ]


def test_without_related_claims_are_checked_per_ledger(pair: tuple[str, str]) -> None:
    first, _second = split_claim(pair)
    third = str(Path(first).with_name("third.jsonl"))
    ledger.create_ledger(third, WORK)
    stored = add(third, claim_id="C-0001", claim="Another wording.")
    assert stored["claim_id"] == "C-0001"
    assert ledger.validate_ledger(third) == []
    assert ledger.validate_ledger(third, [first]) != []


def fail_second_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    real = os.replace
    calls: list[int] = []

    def flaky(src: Any, dst: Any) -> None:
        calls.append(1)
        if len(calls) == 2:
            raise OSError("disk full")
        real(src, dst)

    monkeypatch.setattr(os, "replace", flaky)


def test_update_records_write_error_restores_all_files(
    pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = split_claim(pair)
    before = snapshot(first, second)
    fail_second_replace(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        ledger.update_records(
            first, [{"id": "R-0001", "changes": {"claim": "New wording."}}], [second]
        )
    assert snapshot(first, second) == before
    assert not list(Path(first).parent.glob("*.tmp"))


def test_move_record_write_error_leaves_no_duplicate(
    pair: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    first, second = pair
    add_related(first, [second])
    before = snapshot(first, second)
    fail_second_replace(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        ledger.move_record(first, "R-0001", second)
    assert snapshot(first, second) == before
    assert not list(Path(first).parent.glob("*.tmp"))


def test_update_records_names_every_item_touching_a_failing_record(
    pair: tuple[str, str],
) -> None:
    first, second = split_claim(pair)
    rewrite_line(first, 0, {"ledger": {**ledger.read(first)[0], "notes": RECORD["quote"]}})
    before = snapshot(first, second)
    with pytest.raises(ValueError, match=r"updates\[0, 1, 2\] \(R-0001\)"):
        ledger.update_records(
            first,
            [
                {"id": "R-0001", "changes": {"claim": "One."}},
                {"id": "R-0001", "changes": {"claim": "Two."}},
                {"id": "R-0001", "changes": {"claim": "Three."}},
            ],
            [second],
        )
    assert snapshot(first, second) == before
