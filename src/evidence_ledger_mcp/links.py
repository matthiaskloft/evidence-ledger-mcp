"""Resolve a ledger's sources against the reader's own PDFs and write a local link file."""

from __future__ import annotations

import bisect
import datetime
import hashlib
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evidence_ledger_mcp import checks, fetch, ledger

MAX_FILES = 5000
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_CANDIDATES = 20000  # spans hashed per record; masked quotes with common edge words
MAX_SPAN = 20000  # normalized characters between a quote's first and last words
MIN_TITLE = 20  # normalized characters; shorter titles could match by chance
FRONT_PAGES = 2
ISBN_PAGES = 10
STATUSES = ("found", "passage_not_found", "source_not_found", "not_searchable")


class _Library:
    """The PDFs of a folder; each is read at most once, and only when needed."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.files = sorted(p for p in folder.rglob("*") if p.suffix.lower() == ".pdf")
        if len(self.files) > MAX_FILES:
            raise ValueError(f"{folder}: more than {MAX_FILES} PDFs")
        self.pages: dict[Path, list[str]] = {}
        self.unreadable: dict[str, str] = {}
        self.front: dict[Path, tuple[str, str, str]] = {}

    def read(self, file: Path) -> list[str] | None:
        if file not in self.pages and str(file) not in self.unreadable:
            try:
                if file.stat().st_size > MAX_FILE_BYTES:
                    raise fetch.FetchError("too large")
                self.pages[file] = fetch.pdf_pages(file.read_bytes())
            except fetch.FetchError as exc:
                self.unreadable[str(file)] = str(exc)
            except OSError:
                self.unreadable[str(file)] = "not readable"
        return self.pages.get(file)

    def fronts(self) -> Iterator[tuple[Path, tuple[str, str, str]]]:
        """Each readable PDF with its front matter prepared for DOI, ISBN and title matching."""
        for file in self.files:
            if file not in self.front and (pages := self.read(file)) is not None:
                self.front[file] = (
                    _doi_text("\n".join(pages[:FRONT_PAGES])),
                    re.sub(r"[^0-9Xx]", "", "".join(pages[:ISBN_PAGES])).upper(),
                    ledger.normalize("".join(pages[:FRONT_PAGES])),
                )
            if file in self.front:
                yield file, self.front[file]


def _title(value: str) -> str:
    """A title normalized for matching, without LaTeX commands; empty if too short to be safe."""
    title = ledger.normalize(re.sub(r"\\[A-Za-z]+", "", value))
    return title if len(title) >= MIN_TITLE else ""


def _doi_text(text: str) -> str:
    """Front matter for DOI matching, twice: with line breaks as spaces, and with them removed,
    so that a DOI wrapped across lines is found too."""
    spaced = re.sub(r"\s+", " ", text)
    joined = re.sub(r"\s*\n\s*", "", text)
    return f"{spaced}\0{joined}".casefold()


def _has_doi(doi: str, text: str) -> bool:
    """Whether the text holds the complete DOI, not merely a longer one starting with it."""
    return re.search(re.escape(doi) + r"(?![\w/-]|\.\w)", text) is not None


def _identifiers(
    records: list[ledger.Record], entry: dict[str, str]
) -> tuple[set[str], set[str], str]:
    """DOIs, ISBNs and the normalized title of a source, from its records and its bibliography
    entry; the entry's BibTeX (`doi`) or CSL JSON (`DOI`) names are both read."""
    dois = {r["doi"] for r in records if isinstance(r.get("doi"), str)}
    isbns = {r["isbn"] for r in records if isinstance(r.get("isbn"), str)}
    for name, found in (("doi", dois), ("isbn", isbns)):
        if value := entry.get(name) or entry.get(name.upper()):
            found.add(value)
    doi_set = {re.sub(r"\s+", "", d).removeprefix("https://doi.org/").casefold() for d in dois}
    isbn_set = {re.sub(r"[^0-9Xx]", "", i).upper() for i in isbns} - {""}
    return doi_set, isbn_set, _title(entry.get("title", ""))


def _match(
    key: str, records: list[ledger.Record], entry: dict[str, str], library: _Library
) -> Path | None:
    """The PDF of a source, by the first of: its DOI on the PDF's first pages, its ISBN on the
    front matter, its title on the first pages, or a file named after its key. A DOI or title
    must match one PDF only; DOIs and titles are looked for on the first pages, so that a PDF
    merely citing the source in its references does not match."""
    dois, isbns, title = _identifiers(records, entry)
    for kind, needles in enumerate((dois, isbns, {title} - {""})):
        hits = (
            [
                file
                for file, front in library.fronts()
                if any(
                    _has_doi(needle, front[kind]) if kind == 0 else needle in front[kind]
                    for needle in needles
                )
            ]
            if needles
            else []
        )
        if len(hits) == 1:
            return hits[0]
    named = [
        file
        for file in library.files
        if file.stem.casefold() == key.casefold() and library.read(file) is not None
    ]
    return named[0] if len(named) == 1 else None  # several, e.g. two editions: none is safe


def _occurrences(text: str, piece: str) -> list[int]:
    found: list[int] = []
    pos = text.find(piece)
    while pos >= 0:
        found.append(pos)
        pos = text.find(piece, pos + 1)
    return found


def _find(record: ledger.Record, pages: list[str]) -> int | None | bool:
    """The 1-based page where the passage starts, None if it is not there, or False if the
    record cannot be searched: it needs a quote, whole or masked to its first and last words."""
    quote = record.get("quote")
    version, _, digest = str(record.get("quote_hash", "")).partition(":")
    if not isinstance(quote, str) or version not in ("sha256-n1", "sha256-n2"):
        return False
    norm = version.removeprefix("sha256-")
    whole = ledger.normalize(quote, norm)
    is_whole = hashlib.sha256(whole.encode("utf-8")).hexdigest() == digest
    # A quote matching its hash whole is searched as recorded, an ellipsis in it being part of
    # the source; otherwise "…" marks the words a masked export left out.
    masked = [ledger.normalize(s, norm) for s in quote.strip().split("…")]
    pieces = [whole] if is_whole else masked
    if not pieces[0] or not pieces[-1]:
        return False
    normalized = [ledger.normalize(page, norm) for page in pages]
    text = "".join(normalized)
    starts = [0]
    for page in normalized:
        starts.append(starts[-1] + len(page))
    if is_whole and (pos := text.find(whole)) >= 0:
        return bisect.bisect_right(starts, pos)  # a whole quote needs no span limit
    ends = [pos + len(pieces[-1]) for pos in _occurrences(text, pieces[-1])]
    budget = MAX_CANDIDATES
    for start in _occurrences(text, pieces[0]):
        first = bisect.bisect_left(ends, start + len(pieces[0]))
        last = bisect.bisect_right(ends, start + MAX_SPAN)
        budget -= last - first
        if budget < 0:
            return None  # edge words too common to tell the passage apart
        for end in ends[first:last]:
            if hashlib.sha256(text[start:end].encode("utf-8")).hexdigest() == digest:
                return bisect.bisect_right(starts, start)
    return None


def resolve_links(
    path: str,
    folder: str,
    link_file: str,
    bibliography: str | None = None,
    include_withdrawn: bool = False,
) -> dict[str, Any]:
    """Match each record's source to a PDF in `folder`, find its passage by `quote_hash`, and
    write the result to `link_file`; returns record ids by status, never source text."""
    root = Path(folder).resolve()
    if not root.is_dir():
        raise ValueError(f"{folder}: not a folder")
    target = Path(link_file).resolve()
    if target.suffix.lower() != ".json":
        raise ValueError("link_file must end in .json")
    if target == Path(path).resolve():
        raise ValueError("link_file must not be the ledger")
    if bibliography and target == Path(bibliography).resolve():
        raise ValueError("link_file must not be the bibliography")
    _, all_records = ledger.read(path)
    rows = [
        (str(r.get("id", f"record {n}")), r)
        for n, r in enumerate(all_records, 1)
        if include_withdrawn or "withdrawn" not in r
    ]
    by_key: dict[str, list[ledger.Record]] = {}
    for _, record in rows:
        if isinstance(record.get("key"), str):
            by_key.setdefault(record["key"], []).append(record)

    entries = checks.bibliography(bibliography) if bibliography else {}
    library = _Library(root)
    files = {
        key: _match(key, records, entries.get(key, {}), library) for key, records in by_key.items()
    }
    links: dict[str, dict[str, Any]] = {}
    for label, record in rows:
        key = record.get("key")
        file = files.get(key) if isinstance(key, str) else None
        if file is None:
            links[label] = {"status": "source_not_found"}
            continue
        page = _find(record, library.pages[file])
        link: dict[str, Any] = {"file": str(file)}
        if page is False:
            link["status"] = "not_searchable"
        elif page is None:
            link["status"] = "passage_not_found"
        else:
            link.update(status="found", page=page)
        links[label] = link

    target.write_text(
        json.dumps(
            {
                "ledger": str(Path(path).resolve()),
                "folder": str(root),
                "created": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds"),
                "records": links,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        "utf-8",
    )
    result: dict[str, Any] = {"records": len(rows), "link_file": str(target)}
    for status in STATUSES:
        result[status] = [label for label, link in links.items() if link["status"] == status]
    result["unreadable_files"] = library.unreadable
    return result
