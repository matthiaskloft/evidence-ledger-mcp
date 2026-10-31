from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import export, ledger, links

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
    "locator": {"page": 2},
    "quote": QUOTE,
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}


def make_pdf(*pages: list[str]) -> bytes:
    """A minimal PDF with one page per list of Helvetica text lines."""
    count = len(pages)
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids ["
        + " ".join(f"{4 + 2 * i} 0 R" for i in range(count))
        + f"] /Count {count} >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, lines in enumerate(pages):
        stream = "".join(
            f"BT /F1 12 Tf 50 {700 - 20 * n} Td ({s}) Tj ET\n" for n, s in enumerate(lines)
        )
        objects.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            f" /Contents {5 + 2 * i} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n{stream}endstream")
    out = b"%PDF-1.4\n"
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{offset:010d} 00000 n \n" for offset in offsets).encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out


ARTICLE = make_pdf(["Example study", "doi: 10.1000/EXAMPLE"], ["Results", QUOTE.upper() + "."])


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    return target


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / "pdfs" / "sub").mkdir(parents=True)
    return tmp_path / "pdfs"


def add(path: str, **changes: Any) -> str:
    record = {k: v for k, v in {**RECORD, **changes}.items() if v is not None}
    return str(ledger.add_record(path, record, PROVENANCE)["id"])


def resolve(path: str, folder: Path, **kwargs: Any) -> dict[str, Any]:
    return links.resolve_links(path, str(folder), str(folder.parent / "links.json"), **kwargs)


def test_passage_found_by_doi_with_page(path: str, folder: Path) -> None:
    add(path)
    (folder / "sub" / "article.pdf").write_bytes(ARTICLE)
    result = resolve(path, folder)
    assert result["found"] == ["R-0001"]
    saved = json.loads((folder.parent / "links.json").read_text("utf-8"))
    assert saved["records"]["R-0001"] == {
        "file": str((folder / "sub" / "article.pdf").resolve()),
        "status": "found",
        "page": 2,
    }
    assert QUOTE not in json.dumps(result)


def test_source_matched_by_key_file_name(path: str, folder: Path) -> None:
    add(path, doi=None, url="https://example.org/study")
    (folder / "ExampleStudy2026.PDF").write_bytes(make_pdf(["Results", QUOTE]))
    assert resolve(path, folder)["found"] == ["R-0001"]


def test_source_matched_by_isbn(path: str, folder: Path) -> None:
    add(path, doi=None, isbn="978-3-16-148410-0")
    (folder / "book.pdf").write_bytes(make_pdf(["ISBN 978 3 16 148410 0"], [QUOTE]))
    assert resolve(path, folder)["found"] == ["R-0001"]


def test_masked_quote_is_found(path: str, folder: Path) -> None:
    add(path)
    record = export.export_record(ledger.get_record(path, "R-0001"), "masked")
    ledger._rewrite(path, ledger.read(path)[0], [record])
    assert "…" in ledger.get_record(path, "R-0001")["quote"]
    (folder / "article.pdf").write_bytes(ARTICLE)
    assert resolve(path, folder)["found"] == ["R-0001"]


def test_statuses(path: str, folder: Path) -> None:
    add(path)
    add(path, quote="Ledger records reduced unchecked citations from 40 to 4 per manuscript")
    add(path, key="otherStudy", doi="10.1000/other")
    add(path, quote="… unchecked citations from 40 …")
    (folder / "article.pdf").write_bytes(ARTICLE)
    (folder / "broken.pdf").write_bytes(b"%PDF-1.4 not really")
    result = resolve(path, folder)
    assert result["found"] == ["R-0001", "R-0004"]  # an ellipsis recorded as part of the quote
    assert result["passage_not_found"] == ["R-0002"]
    assert result["source_not_found"] == ["R-0003"]
    assert result["not_searchable"] == []
    assert result["unreadable_files"] == {str((folder / "broken.pdf").resolve()): "unreadable pdf"}


def test_withdrawn_records_are_skipped(path: str, folder: Path) -> None:
    add(path)
    ledger.withdraw_record(path, "R-0001", "Superseded.")
    assert resolve(path, folder)["records"] == 0
    assert resolve(path, folder, include_withdrawn=True)["source_not_found"] == ["R-0001"]


def test_bad_arguments(path: str, folder: Path) -> None:
    with pytest.raises(ValueError, match="not a folder"):
        links.resolve_links(path, str(folder / "missing"), str(folder / "l.json"))
    with pytest.raises(ValueError, match=r".json"):
        links.resolve_links(path, str(folder), str(folder / "links.txt"))


def test_file_names_do_not_matter_with_doi_or_title(path: str, folder: Path) -> None:
    add(path, doi=None, url="https://example.org/study")
    (folder / "Smith et al. - 2026 - final version.pdf").write_bytes(
        make_pdf(["Ledgers Reduce Unchecked Citations in Manuscripts"], [QUOTE])
    )
    bib = folder.parent / "refs.bib"
    bib.write_text(
        "@article{exampleStudy2026,\n  title = {Ledgers {Reduce} \\emph{Unchecked} Citations"
        " in Manuscripts},\n  year = 2026\n}\n",
        "utf-8",
    )
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]
    assert resolve(path, folder, bibliography=str(bib))["found"] == ["R-0001"]


def test_doi_from_csl_json(path: str, folder: Path) -> None:
    add(path, doi=None, url="https://example.org/study")
    (folder / "x.pdf").write_bytes(ARTICLE)
    csl = folder.parent / "refs.json"
    csl.write_text(json.dumps([{"id": "exampleStudy2026", "DOI": "10.1000/example"}]), "utf-8")
    assert resolve(path, folder, bibliography=str(csl))["found"] == ["R-0001"]


def test_doi_in_references_of_another_pdf_does_not_match(path: str, folder: Path) -> None:
    add(path)
    citing = make_pdf(["Another paper"], ["Body"], ["References", "doi: 10.1000/example"])
    (folder / "citing.pdf").write_bytes(citing)
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]


def test_ambiguous_doi_does_not_match(path: str, folder: Path) -> None:
    add(path)
    (folder / "a.pdf").write_bytes(ARTICLE)
    (folder / "b.pdf").write_bytes(ARTICLE)
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]


def test_quote_with_leading_ellipsis_is_found_whole(path: str, folder: Path) -> None:
    add(path, quote="… " + QUOTE)
    (folder / "article.pdf").write_bytes(ARTICLE)
    assert resolve(path, folder)["found"] == ["R-0001"]


def test_common_edge_words_are_bounded(
    path: str, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    add(path, quote="Ledger … manuscript")
    record = ledger.get_record(path, "R-0001")
    monkeypatch.setattr(links, "MAX_CANDIDATES", 3)
    pages = [" ".join(["Ledger x manuscript"] * 5)]
    assert links._find(record, pages) is None


def test_doi_wrapped_across_lines(path: str, folder: Path) -> None:
    add(path)
    pdf = make_pdf(["Example study", "https://doi.org/10.1000/", "example Received 2026"], [QUOTE])
    (folder / "x.pdf").write_bytes(pdf)
    assert resolve(path, folder)["found"] == ["R-0001"]


def test_longer_doi_does_not_match(path: str, folder: Path) -> None:
    add(path)
    (folder / "x.pdf").write_bytes(make_pdf(["doi: 10.1000/example2."], [QUOTE]))
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]
    (folder / "y.pdf").write_bytes(make_pdf(["doi: 10.1000/example."], [QUOTE]))
    assert resolve(path, folder)["found"] == ["R-0001"]


def test_link_file_must_not_be_the_bibliography(path: str, folder: Path) -> None:
    bib = folder.parent / "refs.json"
    bib.write_text("[]", "utf-8")
    with pytest.raises(ValueError, match="bibliography"):
        links.resolve_links(path, str(folder), str(bib), bibliography=str(bib))
    assert bib.read_text("utf-8") == "[]"


def test_two_pdfs_named_after_the_key_match_neither(path: str, folder: Path) -> None:
    add(path, doi=None, url="https://example.org/study")
    pdf = make_pdf(["Results", QUOTE])
    (folder / "exampleStudy2026.pdf").write_bytes(pdf)
    (folder / "sub" / "exampleStudy2026.pdf").write_bytes(pdf)
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]


def test_very_long_whole_quote_is_found() -> None:
    quote = " ".join(f"word{n}" for n in range(5000))
    record = {"quote": quote, "quote_hash": ledger.quote_hash(quote)}
    assert links._find(record, ["Intro.", quote]) == 2
