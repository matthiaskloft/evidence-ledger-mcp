"""Link resolution against real open-access PDFs, fetched and cached by `real_pdfs`."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from real_pdfs import real_pdf

from evidence_ledger_mcp import ledger, links, summary

pytestmark = pytest.mark.network

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
IOANNIDIS = {"key": "ioannidis2005", "doi": "10.1371/journal.pmed.0020124"}
MISTRAL = {"key": "jiang2023mistral", "url": "https://arxiv.org/abs/2310.06825"}
SULPIS = {"key": "sulpis2022", "doi": "10.5194/gmd-15-2105-2022"}
BIB = """@article{jiang2023mistral,
  title = {Mistral 7B},
  author = {Jiang, Albert Q. and Sablayrolles, Alexandre and Mensch, Arthur},
  year = {2023}
}
"""
# Quotes as a reader copies them from the PDF: plain "fi", whole words, normal spacing.
WITHIN_PAGE = "It can be proven that most claimed research findings are false."
HYPHENATED = (
    "Fields considered highly informative and creative given the wealth of the assembled and"
    " tested information, such as microarrays and other high-throughput discovery-oriented"
    " research [4,8,17], should have extremely low PPV."
)
# Page 1 ends mid-sentence; the sidebar (title, citation, licence, affiliations) and page 2's
# running head come between the two halves in the extracted text.
ACROSS_SIDEBAR = "A research finding is thus more likely true than false if (1 − β)R > α."  # noqa: RUF001
# Leaves out the sentence between the two without marking it: a misquote.
OMISSION = (
    "However, this should not be surprising. Here I will examine the key factors that influence"
    " this problem and some corollaries thereof."
)
SLIDING_WINDOW = (
    "Sliding Window Attention. SWA exploits the stacked layers of a transformer to attend"
    " information beyond the window size W."
)
ABSTRACT = (
    "RADI combines CaCO3 dissolution driven by organic matter degradation with a diffusive"
    " boundary layer and integrates state-of-the-art parameterizations of CaCO3 dissolution"
    " kinetics in seawater"
)
# Page 2 ends with "in-"; the footer, page 3's running head and a figure caption follow.
ACROSS_CAPTION = (
    "Tables 1 and 2 include an inventory of model variables and parameters and a list of"
    " nomenclature for chemical species, respectively."
)


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """The PDFs under the kind of names readers give them, in nested folders."""
    folder = tmp_path / "papers"
    names = {
        "ioannidis2005.pdf": "Medicine/Ioannidis - 2005 - Why most published research.pdf",
        "mistral7b-2023.pdf": "LLM/2310.06825v1.pdf",
        "sulpis2022-radi.pdf": "Ocean/gmd-15-2105-2022 (1).pdf",
    }
    for fixture, name in names.items():
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(real_pdf(fixture), folder / name)
    return folder


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    return target


def add(path: str, source: dict[str, Any], page: str, quote: str | None) -> str:
    """A record; one without a quote is a non-contestable claim citing a page only."""
    record = {
        "claim": "A claim.",
        "claim_type": "empirical",
        "contestable": quote is not None,
        "anchor": {"exact": "a claim"},
        **source,
        "locator": {"page": page},
        "relation": "supports",
        "justification": "The passage says so.",
        "retrieved_via": "pdf",
        **({"quote": quote} if quote else {"contestable_reason": "Background fact."}),
    }
    return str(ledger.add_record(path, record, PROVENANCE)["id"])


def resolve(path: str, library: Path, bib: str | None = None) -> tuple[dict[str, Any], Any]:
    link_file = library.parent / "links.private.json"
    result = links.resolve_links(path, str(library), str(link_file), bib)
    return result, json.loads(link_file.read_text("utf-8"))["records"]


def write_bib(library: Path) -> str:
    bib = library.parent / "refs.bib"
    bib.write_text(BIB, "utf-8")
    return str(bib)


def test_real_pdfs_are_matched_and_passages_found(path: str, library: Path) -> None:
    within = add(path, IOANNIDIS, "696", WITHIN_PAGE)
    hyphen = add(path, IOANNIDIS, "698", HYPHENATED)
    sidebar = add(path, IOANNIDIS, "696", ACROSS_SIDEBAR)
    window = add(path, MISTRAL, "2", SLIDING_WINDOW)
    abstract = add(path, SULPIS, "2105", ABSTRACT)
    caption = add(path, SULPIS, "2106", ACROSS_CAPTION)
    result, records = resolve(path, library, write_bib(library))
    assert result["found"] == [within, hyphen, sidebar, window, abstract, caption]
    assert result["unreadable_files"] == {}
    pages = {
        rid: (records[rid]["page"], records[rid].get("across_pages", False)) for rid in records
    }
    assert pages == {
        within: (1, False),
        hyphen: (3, False),
        sidebar: (1, True),
        window: (2, False),
        abstract: (1, False),
        caption: (2, True),
    }
    assert Path(records[window]["file"]).name == "2310.06825v1.pdf"


def test_a_silent_omission_is_not_found(path: str, library: Path) -> None:
    rid = add(path, IOANNIDIS, "696", OMISSION)
    result, records = resolve(path, library)
    assert result["passage_not_found"] == [rid]
    assert records[rid]["page"] == 1 and records[rid]["page_from"] == "page_label"


def test_short_title_needs_the_bibliography_author(path: str, library: Path) -> None:
    rid = add(path, MISTRAL, "2", SLIDING_WINDOW)
    assert resolve(path, library)[0]["source_not_found"] == [rid]  # no DOI printed, no title
    other = library.parent / "other.bib"
    other.write_text(BIB.replace("Jiang, Albert Q.", "Smith, Jane"), "utf-8")
    assert resolve(path, library, str(other))[0]["source_not_found"] == [rid]
    assert resolve(path, library, write_bib(library))[0]["found"] == [rid]


def test_relink_masked_and_locator_exports(path: str, library: Path) -> None:
    within = add(path, IOANNIDIS, "696", WITHIN_PAGE)
    caption = add(path, SULPIS, "2106", ACROSS_CAPTION)
    cited = add(path, SULPIS, "2107", None)
    for level in ("masked", "locator"):
        original = library.parent / f"summary-{level}.html"
        summary.summarize_ledger(path, str(original), level)
        result = links.relink_html(str(original), str(library))
        html = Path(result["path"]).read_text("utf-8")
        if level == "masked":
            assert result["found"] == [within]
            # A masked quote cannot be followed across a page break; the cited page serves.
            assert result["passage_not_found"] == [caption]
        else:
            assert result["not_searchable"] == [within, caption, cited]
        assert "papers/Ocean/gmd-15-2105-2022%20%281%29.pdf#page=3" in html  # page 2107
        assert "Why%20most%20published%20research.pdf#page=1" in html
