"""Resolve a ledger's sources against the reader's own PDFs and write a local link file."""

from __future__ import annotations

import bisect
import datetime
import hashlib
import json
import re
from collections.abc import Iterator
from html import escape, unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from evidence_ledger_mcp import checks, fetch, ledger

MAX_FILES = 5000
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_SPAN = 20000  # normalized characters between a quote's first and last words
MIN_TITLE = 20  # normalized characters; shorter titles could match by chance
FRONT_PAGES = 2
ISBN_PAGES = 10
PRIVATE_JSON = ".private.json"
PRIVATE_HTML = ".private.html"
NOTICE = (
    "Private: this links to files on this computer. Do not share or publish it; share the"
    " original instead."
)
BANNER = (
    '<div class="el-private" role="note" style="background:#fde68a;color:#422006;'
    'padding:.6em 1em;font:600 15px/1.4 system-ui,sans-serif;border-bottom:2px solid #b45309">'
    f"{NOTICE}</div>"
)
NOINDEX = '<meta name="robots" content="noindex">'
_DATA = re.compile(
    r'<script type="application/json" id="evidence-ledger-data">(.*?)</script>', re.DOTALL
)
_RECORD_HEAD = re.compile(r'(<article class="record" data-record="([^"]*)">.*?</div>)', re.DOTALL)
_TITLE = re.compile(r"<title[^>]*>", re.IGNORECASE)
_BODY = re.compile(r"<body[^>]*>", re.IGNORECASE)
_HEAD = re.compile(r"<head[^>]*>", re.IGNORECASE)
STATUSES = ("found", "passage_not_found", "source_not_found", "not_searchable")


class _Library:
    """The PDFs of a folder; each is read at most once, and only when needed."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.files = sorted(p for p in folder.rglob("*") if p.suffix.lower() == ".pdf")
        if len(self.files) > MAX_FILES:
            raise ValueError(f"{folder}: more than {MAX_FILES} PDFs")
        self.pages: dict[Path, fetch.Pdf] = {}
        self.unreadable: dict[str, str] = {}
        self.front: dict[Path, tuple[str, str, str]] = {}

    def read(self, file: Path) -> fetch.Pdf | None:
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
            if file not in self.front and (pdf := self.read(file)) is not None:
                self.front[file] = (
                    "\n".join(pdf.pages[:FRONT_PAGES]).casefold(),
                    re.sub(r"[^0-9Xx]", "", "".join(pdf.pages[:ISBN_PAGES])).upper(),
                    ledger.normalize("".join(pdf.pages[:FRONT_PAGES])),
                )
            if file in self.front:
                yield file, self.front[file]


def _title(value: str) -> str:
    """A title normalized for matching, without LaTeX commands; empty if too short to be safe."""
    title = ledger.normalize(re.sub(r"\\[A-Za-z]+", "", value))
    return title if len(title) >= MIN_TITLE else ""


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
    doi_set = {d.strip().removeprefix("https://doi.org/").casefold() for d in dois}
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
                if any(needle in front[kind] for needle in needles)
            ]
            if needles
            else []
        )
        if len(hits) == 1:
            return hits[0]
    for file in library.files:
        if file.stem.casefold() == key.casefold() and library.read(file) is not None:
            return file
    return None


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
    segments = quote.strip().split("…")
    pieces = [ledger.normalize(s, norm) for s in segments]
    if not pieces[0] or not pieces[-1]:
        return False
    normalized = [ledger.normalize(page, norm) for page in pages]
    text = "".join(normalized)
    starts = [0]
    for page in normalized:
        starts.append(starts[-1] + len(page))
    ends = [pos + len(pieces[-1]) for pos in _occurrences(text, pieces[-1])]
    for start in _occurrences(text, pieces[0]):
        first = bisect.bisect_left(ends, start + len(pieces[0]))
        last = bisect.bisect_right(ends, start + MAX_SPAN)
        for end in ends[first:last]:
            if hashlib.sha256(text[start:end].encode("utf-8")).hexdigest() == digest:
                return bisect.bisect_right(starts, start)
    return None


def _locator_page(record: ledger.Record, pdf: fetch.Pdf) -> tuple[int, str] | None:
    """The PDF page of the record's `locator.page`: by the PDF's printed page labels, or, in a
    PDF without labels, by number, which is right only where printed and PDF pages coincide."""
    locator = record.get("locator")
    page = str(locator.get("page", "")) if isinstance(locator, dict) else ""
    if page and pdf.labels:
        return (pdf.labels.index(page) + 1, "page_label") if page in pdf.labels else None
    if page.isdigit() and 1 <= int(page) <= len(pdf.pages):
        return int(page), "page_number"
    return None


def _resolve(
    rows: list[tuple[str, ledger.Record]], root: Path, bibliography: str | None
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Each record's link (status, file and page, with where the page came from) and the PDFs
    that could not be read."""
    if not root.is_dir():
        raise ValueError(f"{root}: not a folder")
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
        pdf = library.pages[file]
        page = _find(record, pdf.pages)
        link: dict[str, Any] = {"file": str(file)}
        if page is False or page is None:
            link["status"] = "not_searchable" if page is False else "passage_not_found"
            if located := _locator_page(record, pdf):
                link.update(page=located[0], page_from=located[1])
        else:
            link.update(status="found", page=page, page_from="passage")
        links[label] = link
    return links, library.unreadable


def _summary(links: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        status: [label for label, link in links.items() if link["status"] == status]
        for status in STATUSES
    }


def _rows(records: list[Any], include_withdrawn: bool) -> list[tuple[str, ledger.Record]]:
    return [
        (str(r.get("id", f"record {n}")), r)
        for n, r in enumerate(records, 1)
        if isinstance(r, dict) and (include_withdrawn or "withdrawn" not in r)
    ]


def resolve_links(
    path: str,
    folder: str,
    link_file: str,
    bibliography: str | None = None,
    include_withdrawn: bool = False,
) -> dict[str, Any]:
    """Match each record's source to a PDF in `folder`, find its passage by `quote_hash`, and
    write the result to `link_file`, whose name must mark it private; returns record ids by
    status, never source text."""
    target = Path(link_file).resolve()
    if not target.name.lower().endswith(PRIVATE_JSON):
        raise ValueError(f"link_file must end in {PRIVATE_JSON}: it is private to this computer")
    root = Path(folder).resolve()
    _, all_records = ledger.read(path)
    rows = _rows(all_records, include_withdrawn)
    links, unreadable = _resolve(rows, root, bibliography)
    target.write_text(
        json.dumps(
            {
                "private": NOTICE,
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
    return {
        "records": len(rows),
        "link_file": str(target),
        "notice": NOTICE,
        **_summary(links),
        "unreadable_files": unreadable,
    }


def _href(file: Path, base: Path, page: int | None) -> str:
    """A link relative to the copy's folder when the PDF is inside it, so that the copy and
    its PDFs can move together; otherwise an absolute file:// link."""
    try:
        href = quote(file.relative_to(base).as_posix())
    except ValueError:
        href = file.as_uri()
    return f"{href}#page={page}" if page else href


def _copy_link(link: dict[str, Any], base: Path) -> str:
    if "file" not in link:
        return ""
    file = Path(link["file"])
    page = link.get("page")
    where = {
        "passage": f", PDF page {page}, passage found",
        "page_label": f", PDF page {page}, from the cited page",
        "page_number": f", PDF page {page}, assuming the cited page number",
    }.get(link.get("page_from", ""), "")
    href = escape(_href(file, base, page))
    return (
        f'<p class="el-copy"><b>Your copy:</b> <a href="{href}">{escape(file.name)}</a>'
        f"{escape(where)}</p>"
    )


def relink_html(html: str, folder: str, bibliography: str | None = None) -> dict[str, Any]:
    """Write a private copy of a summary or embedded HTML file from this server, whose evidence
    cards link to the reader's own PDFs in `folder`; the copy is named `<name>.private.html`,
    next to the original, and is marked private in its title and a banner."""
    source = Path(html).resolve()
    if source.name.lower().endswith(PRIVATE_HTML):
        raise ValueError("this is already a private copy: relink the original instead")
    text = source.read_text("utf-8")
    data = _DATA.search(text)
    if data is None:
        raise ValueError(
            "no ledger data in this HTML: rebuild it with summarize_ledger or embed_ledger"
        )
    try:
        records = json.loads(data.group(1))["records"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("the ledger data in this HTML cannot be read") from exc
    if not isinstance(records, list):
        raise ValueError("the ledger data in this HTML cannot be read")
    rows = _rows(records, include_withdrawn=True)
    links, unreadable = _resolve(rows, Path(folder).resolve(), bibliography)
    target = source.with_name(source.name[: -len(source.suffix)] + PRIVATE_HTML)
    base = target.parent

    def add_link(match: re.Match[str]) -> str:
        link = links.get(unescape(match.group(2)), {})
        return match.group(1) + _copy_link(link, base)

    text = _RECORD_HEAD.sub(add_link, text)
    text = _TITLE.sub(lambda m: m.group(0) + "[Private] ", text, count=1)
    if body := _BODY.search(text):
        text = text[: body.end()] + BANNER + text[body.end() :]
    else:
        text = BANNER + text
    if head := _HEAD.search(text):
        text = text[: head.end()] + NOINDEX + text[head.end() :]
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {
        "path": str(target),
        "notice": NOTICE,
        "records": len(rows),
        **_summary(links),
        "unreadable_files": unreadable,
    }
