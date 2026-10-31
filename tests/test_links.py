from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import export, ledger, links, summary

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
    return links.resolve_links(
        path, str(folder), str(folder.parent / "links.private.json"), **kwargs
    )


def test_passage_found_by_doi_with_page(path: str, folder: Path) -> None:
    add(path)
    (folder / "sub" / "article.pdf").write_bytes(ARTICLE)
    result = resolve(path, folder)
    assert result["found"] == ["R-0001"]
    saved = json.loads((folder.parent / "links.private.json").read_text("utf-8"))
    assert saved["records"]["R-0001"] == {
        "file": str((folder / "sub" / "article.pdf").resolve()),
        "status": "found",
        "page": 2,
        "page_from": "passage",
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
        links.resolve_links(path, str(folder / "missing"), str(folder / "l.private.json"))
    with pytest.raises(ValueError, match="private"):
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


def summary_html(path: str, folder: Path, level: str = "full") -> Path:
    out = folder.parent / f"summary-{level}.html"
    summary.summarize_ledger(path, str(out), level)
    return out


def test_relink_writes_a_private_copy_with_relative_links(path: str, folder: Path) -> None:
    add(path)
    (folder / "sub" / "article.pdf").write_bytes(ARTICLE)
    original = summary_html(path, folder)
    result = links.relink_html(str(original), str(folder))
    copy = Path(result["path"])
    assert copy.name == "summary-full.private.html"
    assert result["found"] == ["R-0001"] and "Do not share" in result["notice"]
    html = copy.read_text("utf-8")
    assert "<title>[Private] " in html and 'class="el-private"' in html
    assert '<meta name="robots" content="noindex">' in html
    assert 'href="pdfs/sub/article.pdf#page=2"' in html
    assert "passage found" in html
    assert "Your copy" not in original.read_text("utf-8")


def test_relink_locator_export_uses_cited_page(path: str, folder: Path) -> None:
    add(path)
    (folder / "article.pdf").write_bytes(ARTICLE)
    result = links.relink_html(str(summary_html(path, folder, "locator")), str(folder))
    assert result["not_searchable"] == ["R-0001"]
    html = Path(result["path"]).read_text("utf-8")
    assert "article.pdf#page=2" in html and "assuming the cited page number" in html


def test_relink_absolute_link_outside_the_copy_folder(
    path: str, folder: Path, tmp_path: Path
) -> None:
    add(path)
    (folder / "article.pdf").write_bytes(ARTICLE)
    elsewhere = tmp_path / "out"
    elsewhere.mkdir()
    original = elsewhere / "s.html"
    summary.summarize_ledger(path, str(original))
    html = Path(links.relink_html(str(original), str(folder))["path"]).read_text("utf-8")
    assert (folder / "article.pdf").resolve().as_uri() + "#page=2" in html


def test_relink_refuses_private_copies_and_html_without_data(path: str, folder: Path) -> None:
    add(path)
    copy = links.relink_html(str(summary_html(path, folder)), str(folder))["path"]
    with pytest.raises(ValueError, match="already a private copy"):
        links.relink_html(copy, str(folder))
    plain = folder.parent / "plain.html"
    plain.write_text("<html><body>Hi</body></html>", "utf-8")
    with pytest.raises(ValueError, match="no ledger data"):
        links.relink_html(str(plain), str(folder))


def test_embedded_data_holds_only_relink_fields(path: str, folder: Path) -> None:
    add(path, note="Private reviewer note")
    html = summary_html(path, folder, "masked").read_text("utf-8")
    assert "Private reviewer note" in html  # the card shows it ...
    data = html.split('id="evidence-ledger-data">')[1].split("</script>")[0]
    assert "Private reviewer note" not in data and "anchor" not in data  # ... the data does not
    assert QUOTE not in data


def test_cited_page_maps_through_page_labels(path: str, folder: Path) -> None:
    import io

    import pypdf

    writer = pypdf.PdfWriter(clone_from=pypdf.PdfReader(io.BytesIO(ARTICLE)))
    writer.set_page_label(0, 1, style=pypdf.constants.PageLabelStyle.DECIMAL, start=346)
    buffer = io.BytesIO()
    writer.write(buffer)
    (folder / "article.pdf").write_bytes(buffer.getvalue())
    add(path, locator={"page": 347})
    result = links.relink_html(str(summary_html(path, folder, "locator")), str(folder))
    html = Path(result["path"]).read_text("utf-8")
    assert "article.pdf#page=2" in html and "from the cited page" in html


def test_link_file_must_not_be_the_ledger(tmp_path: Path, folder: Path) -> None:
    ledger_path = str(tmp_path / "ledger.private.json")
    ledger.create_ledger(ledger_path, WORK)
    with pytest.raises(ValueError, match="must not be the ledger"):
        links.resolve_links(ledger_path, str(folder), ledger_path)
    assert ledger.read(ledger_path)[0]["work"] == WORK


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
    bib = folder.parent / "refs.private.json"
    bib.write_text("[]", "utf-8")
    with pytest.raises(ValueError, match="bibliography"):
        links.resolve_links(path, str(folder), str(bib), bibliography=str(bib))
    assert bib.read_text("utf-8") == "[]"


def test_quote_split_exactly_at_a_page_break_with_a_running_head() -> None:
    quote = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
    record = {"quote": quote, "quote_hash": ledger.quote_hash(quote)}
    pages = [
        "Intro. Ledger records reduced unchecked",
        "Journal of Examples 12 citations from 40 to 3 per manuscript.",
    ]
    found = links._find(record, pages)
    assert isinstance(found, links._Found) and found.page == 1 and found.across_pages


def test_quote_prefix_at_the_end_of_the_pdf_is_not_found() -> None:
    quote = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
    record = {"quote": quote, "quote_hash": ledger.quote_hash(quote)}
    assert links._find(record, ["Intro.", "Ledger records reduced unchecked"]) is None


def test_two_pdfs_named_after_the_key_match_neither(path: str, folder: Path) -> None:
    add(path, doi=None, url="https://example.org/study")
    pdf = make_pdf(["Results", QUOTE])
    (folder / "exampleStudy2026.pdf").write_bytes(pdf)
    (folder / "sub" / "exampleStudy2026.pdf").write_bytes(pdf)
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]


def test_very_long_whole_quote_is_found() -> None:
    quote = " ".join(f"word{n}" for n in range(5000))
    record = {"quote": quote, "quote_hash": ledger.quote_hash(quote)}
    assert links._find(record, ["Intro.", quote]) == links._Found(2)


def test_quote_not_matching_its_hash_is_not_found() -> None:
    record = {"quote": QUOTE, "quote_hash": ledger.quote_hash(QUOTE + " altered")}
    assert links._find(record, [QUOTE]) is None


def test_relink_marks_real_tags_not_tag_like_script_text(path: str, folder: Path) -> None:
    add(path)
    (folder / "article.pdf").write_bytes(ARTICLE)
    original = summary_html(path, folder)
    script = '<script>const t = "<title><head><body>";</script>'
    text = original.read_text("utf-8")
    original.write_text(text.replace("<html", script + "<html", 1), "utf-8")
    html = Path(links.relink_html(str(original), str(folder))["path"]).read_text("utf-8")
    assert script in html
    assert "<title>[Private] " in html and 'class="el-private"' in html


SMITH_BIB = "@article{exampleStudy2026,\n  author = {Smith, Ann},\n  year = 2026\n}\n"


@pytest.mark.parametrize(
    "name", ["Smith 2026.pdf", "smith_2026_ledgers.pdf", "2026-Smith.pdf", "Smith et al 2026.pdf"]
)
def test_pdf_named_after_author_and_year(path: str, folder: Path, name: str) -> None:
    add(path, doi=None, url="https://example.org/study")
    (folder / name).write_bytes(make_pdf(["Results", QUOTE]))
    bib = folder.parent / "refs.bib"
    bib.write_text(SMITH_BIB, "utf-8")
    assert resolve(path, folder)["source_not_found"] == ["R-0001"]
    assert resolve(path, folder, bibliography=str(bib))["found"] == ["R-0001"]


def test_author_year_from_csl_json(path: str, folder: Path) -> None:
    add(path, doi=None, url="https://example.org/study")
    (folder / "van der Berg (2026).pdf").write_bytes(make_pdf(["Results", QUOTE]))
    csl = folder.parent / "refs.json"
    item = {
        "id": "exampleStudy2026",
        "author": [{"family": "van der Berg", "given": "Ann"}],
        "issued": {"date-parts": [[2026, 3]]},
    }
    csl.write_text(json.dumps([item]), "utf-8")
    assert resolve(path, folder, bibliography=str(csl))["found"] == ["R-0001"]


@pytest.mark.parametrize("names", [["Smith 2026a.pdf", "Smith 2026b.pdf"], ["Smith 20260.pdf"]])
def test_author_year_needs_one_exact_match(path: str, folder: Path, names: list[str]) -> None:
    add(path, doi=None, url="https://example.org/study")
    for name in names:
        (folder / name).write_bytes(make_pdf(["Results", QUOTE]))
    bib = folder.parent / "refs.bib"
    bib.write_text(SMITH_BIB, "utf-8")
    assert resolve(path, folder, bibliography=str(bib))["source_not_found"] == ["R-0001"]
