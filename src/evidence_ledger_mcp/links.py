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

from evidence_ledger_mcp import fetch, ledger

MAX_FILES = 5000
MAX_FILE_BYTES = 200 * 1024 * 1024
MAX_SPAN = 20000  # normalized characters between a quote's first and last words
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

    def texts(self) -> Iterator[tuple[Path, list[str]]]:
        for file in self.files:
            if (pages := self.read(file)) is not None:
                yield file, pages


def _identifiers(records: list[ledger.Record]) -> tuple[set[str], set[str]]:
    dois = {r["doi"].casefold() for r in records if isinstance(r.get("doi"), str)}
    isbns = {
        re.sub(r"[ -]", "", r["isbn"]).upper() for r in records if isinstance(r.get("isbn"), str)
    }
    return dois, isbns


def _match(key: str, records: list[ledger.Record], library: _Library) -> Path | None:
    """The PDF named after the key, or else the first whose text holds the DOI or ISBN."""
    for file in library.files:
        if file.stem.casefold() == key.casefold() and library.read(file) is not None:
            return file
    dois, isbns = _identifiers(records)
    if not dois and not isbns:
        return None
    for file, pages in library.texts():
        text = "\n".join(pages)
        compact = re.sub(r"[\s-]", "", text).upper()
        if any(doi in text.casefold() for doi in dois) or any(i in compact for i in isbns):
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


def resolve_links(
    path: str, folder: str, link_file: str, include_withdrawn: bool = False
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

    library = _Library(root)
    files = {key: _match(key, records, library) for key, records in by_key.items()}
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
