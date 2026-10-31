from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import ledger, summary

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
    "locator": {"page": 4, "chunk": {"index": 7, "sha256": "0" * 64}},
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


def add(path: str, **changes: Any) -> dict[str, Any]:
    return ledger.add_record(path, {**RECORD, **changes}, PROVENANCE)


def add_with_note(path: str, note: str) -> None:
    """Add a record, then put a note on it by hand: add_record refuses such notes."""
    add(path)
    lines = Path(path).read_text("utf-8").splitlines()
    lines[-1] = json.dumps({**json.loads(lines[-1]), "note": note})
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")


def write(path: str, **kwargs: Any) -> str:
    out = str(Path(path).parent / "summary.html")
    summary.summarize_ledger(path, out, **kwargs)
    return Path(out).read_text("utf-8")


def test_groups_by_claim_in_order(path: str) -> None:
    add(path, claim="Second claim.", claim_id="C-0002")
    add(path, claim="First claim.", claim_id="C-0001")
    add(path, claim="First claim.", claim_id="C-0001", key="otherStudy2026")
    out = str(Path(path).parent / "summary.html")
    result = summary.summarize_ledger(path, out)
    html = Path(out).read_text("utf-8")
    assert (result["records"], result["claims"], result["level"]) == (3, 2, "full")
    assert html.index("First claim.") < html.index("Second claim.")
    assert html.count("<section") == 2
    assert "<title>Example work: evidence ledger summary</title>" in html
    assert 'href="https://doi.org/10.1000/example"' in html
    assert "page 4" in html
    assert QUOTE in html


def test_escapes_values(path: str) -> None:
    add(path, claim="<script>alert(1)</script>")
    html = write(path)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_withdrawn_only_on_request(path: str) -> None:
    add(path)
    ledger.withdraw_record(path, "R-0001", "Duplicate <b>")
    assert "withdrawn:" not in write(path)
    Path(path).parent.joinpath("summary.html").unlink()
    assert "withdrawn: Duplicate &lt;b&gt;" in write(path, include_withdrawn=True)


def test_masked_hides_middle_of_quote(path: str) -> None:
    add(path)
    html = write(path, level="masked")
    assert "Ledger records" in html
    assert "unchecked citations from 40" not in html


def test_locator_has_no_quote(path: str) -> None:
    add(path)
    assert "<blockquote" not in write(path, level="locator")


def test_leaky_note_writes_nothing(path: str) -> None:
    add_with_note(path, f"Says: {QUOTE.upper()}!")
    out = Path(path).parent / "summary.html"
    with pytest.raises(ValueError, match="R-0001"):
        summary.summarize_ledger(path, str(out), level="masked")
    assert not out.exists()


def test_refuses_to_overwrite_and_bad_arguments(path: str) -> None:
    add(path)
    out = Path(path).parent / "summary.html"
    out.write_text("keep", "utf-8")
    with pytest.raises(FileExistsError):
        summary.summarize_ledger(path, str(out))
    assert out.read_text("utf-8") == "keep"
    with pytest.raises(ValueError, match="differ"):
        summary.summarize_ledger(path, path)
    with pytest.raises(ValueError, match="level"):
        summary.summarize_ledger(path, str(out), level="all")


def test_everything_is_visible_text(path: str) -> None:
    add(path, note="A note.")
    html = write(path)
    assert "title=" not in html.replace("<title>", "")
    assert "<details" not in html
    assert "A note." in html
    assert "@media print" in html and "attr(href)" in html


@pytest.mark.parametrize(
    "url", ["javascript:alert(1)", "data:text/html,danger", "\tJavaScript:alert(1)"]
)
def test_unvalidated_urls_are_not_links(path: str, url: str) -> None:
    add(path)
    lines = Path(path).read_text("utf-8").splitlines()
    record = json.loads(lines[1])
    record["url"] = url
    lines[1] = json.dumps(record)
    Path(path).write_text("\n".join(lines) + "\n", "utf-8")
    html = write(path)
    assert f'href="{url}"' not in html
    assert url in html


def test_annotations_and_header_notes_are_visible(path: str) -> None:
    header = json.loads(Path(path).read_text("utf-8").splitlines()[0])
    header["ledger"].update(description="A ledger description.", notes="A header note.")
    Path(path).write_text(json.dumps(header) + "\n", "utf-8")
    add(
        path,
        importance="critical",
        importance_reason="The result depends on this claim.",
        quote_prefix="Before the passage.",
        quote_suffix="After the passage.",
        found_via={"route": "web_search", "source": "ledger comparison"},
    )
    html = write(path)
    assert "The result depends on this claim." in html
    assert "Before the passage." in html
    assert "After the passage." in html
    assert ledger.quote_hash(QUOTE) in html
    assert "ledger comparison" in html
    assert "A ledger description." in html
    assert "A header note." in html
    Path(path).parent.joinpath("summary.html").unlink()
    masked = write(path, level="masked")
    assert "Before the passage." not in masked
    assert "After the passage." not in masked


def test_grouping_preserves_different_anchors_and_reasons(path: str) -> None:
    add(path, claim_id="C-0001")
    add(
        path,
        claim_id="C-0001",
        anchor={"exact": "Another occurrence in the work."},
        contestable=False,
        contestable_reason="Established background.",
    )
    html = write(path)
    assert "Another occurrence in the work." in html
    assert "Established background." in html
    assert "<b>Contestable:</b> no" in html


@pytest.mark.parametrize("level", ["full", "masked", "locator"])
@pytest.mark.parametrize("exact", [None, "Another claim occurrence."])
def test_grouping_preserves_different_markers(path: str, level: str, exact: str | None) -> None:
    add(path, claim_id="C-0001", anchor={"marker": "Introduction [1]"})
    anchor = {"marker": "Discussion <2>"}
    if exact is not None:
        anchor["exact"] = exact
    add(path, claim_id="C-0001", anchor=anchor)
    html = write(path, level=level)
    assert "<b>Marker:</b> Introduction [1]" in html
    assert "<b>Marker:</b> Discussion &lt;2&gt;" in html
    if exact is not None:
        assert f"<mark>{exact}</mark>" in html
