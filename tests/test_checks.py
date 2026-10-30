from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import checks, ledger

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
QUOTE = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
RECORD: dict[str, Any] = {
    "claim": "Ledgers cut unchecked citations.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "cut unchecked citations"},
    "key": "exampleStudy2026",
    "doi": "10.1000/example",
    "locator": {"page": 4},
    "quote": QUOTE,
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    return target


def add(path: str, provenance: dict[str, Any] | None = None, **changes: Any) -> str:
    record = {k: v for k, v in {**RECORD, **changes}.items() if v is not None}
    return str(ledger.add_record(path, record, {**PROVENANCE, **(provenance or {})})["id"])


def put(path: str, **changes: Any) -> str:
    """Append a record without validation, as a hand-edited ledger can hold."""
    _, existing = ledger.read(path)
    number = len(existing) + 1
    record = {
        **RECORD,
        "id": f"R-{number:04d}",
        "claim_id": f"C-{number:04d}",
        "provenance": {**PROVENANCE, "date": "2026-10-30"},
        **changes,
    }
    record = {k: v for k, v in record.items() if v is not None}
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record) + "\n")
    return str(record.get("id"))


def write(path: str, name: str, text: str) -> str:
    target = Path(path).parent / name
    target.write_text(text, "utf-8")
    return str(target)


def test_clean_ledger_has_empty_gaps(path: str) -> None:
    add(path)
    assert checks.check_ledger(path) == {
        "records": 1,
        "claims": 1,
        "gaps": {"missing_evidence": {}, "claims_without_records": []},
    }


def test_missing_evidence_lists_fields_of_contestable_records(path: str) -> None:
    bare = put(path, locator=None, quote=None, justification=None)
    partial = put(path, quote=None)
    put(path, contestable=False, locator=None)
    gaps = checks.check_ledger(path)["gaps"]
    assert gaps["missing_evidence"] == {
        bare: ["locator", "quote", "justification"],
        partial: ["quote"],
    }


def test_withdrawn_records_are_skipped_unless_included(path: str) -> None:
    first = put(path, locator=None)
    ledger.withdraw_record(path, first, "Wrong source")
    result = checks.check_ledger(path)
    assert result["records"] == 0
    assert result["gaps"]["missing_evidence"] == {}
    included = checks.check_ledger(path, include_withdrawn=True)
    assert included["records"] == 1
    assert included["gaps"]["missing_evidence"] == {first: ["locator"]}


def test_claims_without_records_ignores_include_withdrawn(path: str) -> None:
    gone = add(path)
    add(path)
    other = add(path)
    ledger.withdraw_record(path, gone, "Wrong source")
    ledger.withdraw_record(path, other, "Wrong source")
    for include in (False, True):
        gaps = checks.check_ledger(path, include_withdrawn=include)["gaps"]
        assert gaps["claims_without_records"] == ["C-0001", "C-0003"]
    assert checks.check_ledger(path)["claims"] == 1
    assert checks.check_ledger(path, include_withdrawn=True)["claims"] == 3


def test_a_claim_with_one_live_record_has_records(path: str) -> None:
    first = add(path)
    add(path, claim_id="C-0001")
    ledger.withdraw_record(path, first, "Wrong source")
    assert checks.check_ledger(path)["gaps"]["claims_without_records"] == []


def test_anchors_in_html_span_tags_and_typographic_quotes(path: str) -> None:
    add(path)
    add(path, anchor={"exact": 'said "yes" to it'})
    add(path, anchor={"exact": "absent words"})
    add(path, anchor={"marker": "[1]"})
    html = write(
        path,
        "work.html",
        "<html><head><title>absent words</title></head><body>"
        "<p>Tools did <em>cut unchecked</em> citations.</p>"
        "<p>She said “yes” to it.</p></body></html>",
    )
    anchors = checks.check_ledger(path, work=html)["anchors"]
    assert anchors == {"checked": 3, "not_found": ["R-0003"], "marker_only": ["R-0004"]}


def test_anchors_in_markdown_latex_and_text(path: str) -> None:
    add(path, anchor={"exact": "cut  unchecked\ncitations"})
    add(path, anchor={"exact": "Not there"})
    for name in ("work.qmd", "work.md", "work.tex", "work.txt"):
        work = write(path, name, "We did cut unchecked citations in trials.\n")
        anchors = checks.check_ledger(path, work=work)["anchors"]
        assert anchors == {"checked": 2, "not_found": ["R-0002"], "marker_only": []}


def test_anchors_skip_withdrawn_unless_included(path: str) -> None:
    gone = add(path, anchor={"exact": "Not there"})
    ledger.withdraw_record(path, gone, "Wrong source")
    work = write(path, "work.md", "Text.")
    assert checks.check_ledger(path, work=work)["anchors"]["checked"] == 0
    included = checks.check_ledger(path, work=work, include_withdrawn=True)
    assert included["anchors"]["not_found"] == [gone]


def test_keys_missing_from_bib_file(path: str) -> None:
    add(path)
    add(path, key="otherKey")
    add(path, key="otherKey")
    bib = write(
        path,
        "refs.bib",
        "@string{x = {y}}\n@Comment{otherKey, nope}\n"
        "@ARTICLE{ exampleStudy2026 ,\n  title = {T}\n}\n@book(unusedKey,\n title={B})\n",
    )
    gaps = checks.check_ledger(path, bibliography=bib)["gaps"]
    assert gaps["keys_missing_from_bibliography"] == {"otherKey": ["R-0002", "R-0003"]}


def test_keys_missing_from_csl_json(path: str) -> None:
    add(path)
    add(path, key="otherKey")
    csl = write(path, "refs.json", json.dumps([{"id": "exampleStudy2026", "title": "T"}]))
    gaps = checks.check_ledger(path, bibliography=csl)["gaps"]
    assert gaps["keys_missing_from_bibliography"] == {"otherKey": ["R-0002"]}


def test_html_references_serve_as_bibliography(path: str) -> None:
    add(path)
    add(path, key="otherKey")
    html = write(
        path, "work.html", '<p>cut unchecked citations</p><div id="ref-exampleStudy2026">E.</div>'
    )
    gaps = checks.check_ledger(path, work=html)["gaps"]
    assert gaps["keys_missing_from_bibliography"] == {"otherKey": ["R-0002"]}


def test_explicit_bibliography_beats_html_references(path: str) -> None:
    add(path)
    html = write(path, "work.html", '<div id="ref-other">E.</div>')
    bib = write(path, "refs.bib", "@article{exampleStudy2026, title={T}}")
    gaps = checks.check_ledger(path, work=html, bibliography=bib)["gaps"]
    assert gaps["keys_missing_from_bibliography"] == {}


def test_no_bibliography_known_omits_the_entry(path: str) -> None:
    add(path)
    html = write(path, "work.html", "<p>cut unchecked citations</p>")
    markdown = write(path, "work.md", "cut unchecked citations")
    assert "keys_missing_from_bibliography" not in checks.check_ledger(path)["gaps"]
    for work in (html, markdown):
        assert "keys_missing_from_bibliography" not in checks.check_ledger(path, work=work)["gaps"]


def test_unsupported_bibliography_suffix_is_an_error(path: str) -> None:
    add(path)
    with pytest.raises(ValueError, match=r"\.bib or \.json"):
        checks.check_ledger(path, bibliography=write(path, "refs.yaml", "- id: x"))


def test_csl_json_must_be_a_list(path: str) -> None:
    add(path)
    with pytest.raises(ValueError, match="list"):
        checks.check_ledger(path, bibliography=write(path, "refs.json", "{}"))


def test_revision_lists_different_and_unknown(path: str) -> None:
    add(path, provenance={"manuscript_rev": "abc123"})
    different = add(path, provenance={"manuscript_rev": "old"})
    unknown = add(path)
    revision = checks.check_ledger(path, revision="abc123")["revision"]
    assert revision == {"different": [different], "unknown": [unknown]}
    assert "revision" not in checks.check_ledger(path)


def test_quotes_are_rechecked_against_supplied_sources(path: str) -> None:
    hit = add(path)
    miss = add(path, key="missKey")
    none = add(path, key="noSourceKey")
    bare = add(path, contestable=False, contestable_reason="Background", quote=None)
    sources = {
        "exampleStudy2026": "In the trial, LEDGER RECORDS reduced unchecked citations "
        "from 40 to 3 per manuscript.",
        "missKey": "A different passage altogether.",
    }
    quotes = checks.check_ledger(path, sources=sources)["quotes"]
    assert quotes == {"matched": [hit], "not_found": [miss], "no_source": [none]}
    assert bare not in [i for ids in quotes.values() for i in ids]


def test_result_never_holds_quote_or_source_text(path: str) -> None:
    add(path)
    put(path, key="missKey", locator=None)
    work = write(path, "work.md", "cut unchecked citations")
    sources = {"exampleStudy2026": QUOTE, "missKey": "Secret source passage."}
    result = checks.check_ledger(path, work=work, revision="x", sources=sources)
    dumped = json.dumps(result)
    for text in (QUOTE, "Secret source passage", "unchecked citations", "40 to 3"):
        assert text not in dumped


def test_hand_edited_records_do_not_break_the_check(path: str) -> None:
    put(path, id=None, provenance="oops", quote=5, claim_id=None, locator=None)
    work = write(path, "work.md", "cut unchecked citations")
    result = checks.check_ledger(path, work=work, revision="x", sources={"exampleStudy2026": "a"})
    assert result["gaps"]["missing_evidence"] == {"record 1": ["locator"]}
    assert result["gaps"]["claims_without_records"] == []
    assert result["claims"] == 0
    assert result["revision"] == {"different": [], "unknown": ["record 1"]}
    assert result["quotes"] == {"matched": [], "not_found": [], "no_source": []}


def test_empty_normalized_quote_and_anchor_are_not_found(path: str) -> None:
    quote = put(path, quote="...", anchor={"exact": "   "})
    work = write(path, "work.md", "Some text. ...")
    result = checks.check_ledger(path, work=work, sources={"exampleStudy2026": "Some text. ..."})
    assert result["quotes"]["not_found"] == [quote]
    assert result["anchors"]["not_found"] == [quote]


def test_bib_keys_come_from_line_starts_only(path: str) -> None:
    bib = write(
        path,
        "refs.bib",
        "@article{realKey,\n  note = {see @fake{fakeKey, x}},\n}\n  @book{indented,\n}\n",
    )
    assert checks.bibliography_keys(bib) == {"realKey", "indented"}


def test_bib_comment_blocks_hide_their_entries(path: str) -> None:
    bib = write(
        path,
        "refs.bib",
        "@comment{Removed:\n@article{removedKey,\n  title = {Removed}}\n}\n"
        "@string(jn = {J})\n@article{kept,\n  journal = jn,\n}\n",
    )
    assert checks.bibliography_keys(bib) == {"kept"}


def test_csl_ids_may_be_numbers(path: str) -> None:
    csl = write(path, "refs.json", json.dumps([{"id": 7}, {"id": "a"}, {"id": None}, "x"]))
    assert checks.bibliography_keys(csl) == {"7", "a"}


def test_non_utf8_files_are_an_error(path: str) -> None:
    add(path)
    bad = Path(path).parent / "refs.bib"
    bad.write_bytes(b"@article{caf\xe9,\n}")
    with pytest.raises(ValueError, match="not UTF-8"):
        checks.check_ledger(path, bibliography=str(bad))
    work = Path(path).parent / "work.md"
    work.write_bytes(b"caf\xe9")
    with pytest.raises(ValueError, match="not UTF-8"):
        checks.check_ledger(path, work=str(work))


def test_markup_inside_a_non_html_anchor_is_not_found(path: str) -> None:
    add(path, anchor={"exact": "cut unchecked citations"})
    markdown = write(path, "work.md", "We did cut *unchecked* citations.")
    assert checks.check_ledger(path, work=markdown)["anchors"]["not_found"] == ["R-0001"]
