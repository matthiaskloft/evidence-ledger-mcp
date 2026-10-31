"""Check a ledger against its work, bibliography and sources; reports ids, keys and counts only."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evidence_ledger_mcp import embed, fetch, ledger

HTML_SUFFIXES = (".html", ".htm")
ENTRY_FIELDS = ("locator", "quote", "justification")
_BIB_START = re.compile(r"@\s*(\w+)\s*([{(])")
_BIB_KEY = re.compile(r"\s*([^,\s]+)\s*,")
_BIB_FIELD = re.compile(r"([A-Za-z][\w-]*)\s*=\s*")
_BIB_NON_ENTRIES = {"string", "comment", "preamble"}

Row = tuple[str, ledger.Record]


def _read_text(path: str) -> str:
    try:
        return Path(path).read_text("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path}: not UTF-8") from exc


def _block_end(text: str, pos: int, opening: str) -> int:
    """Position after the block opened by `opening`; braced and quoted values may hold any
    parentheses, and a brace-delimited block counts braces only, as BibTeX does."""
    braces = 1 if opening == "{" else 0
    quoted = False
    while pos < len(text):
        char = text[pos]
        pos += 1
        if char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
            if braces == 0 and opening == "{":
                return pos
        elif opening == "(" and braces == 0:
            if char == '"':
                quoted = not quoted
            elif char == ")" and not quoted:
                return pos
    return pos


def _bib_value(body: str, pos: int) -> str:
    """The value starting at `pos`: braced, quoted or a bare word (e.g. a @string name)."""
    if body.startswith("{", pos):
        return body[pos + 1 : _block_end(body, pos + 1, "{") - 1]
    if body.startswith('"', pos):
        close = body.find('"', pos + 1)
        return body[pos + 1 : close if close >= 0 else len(body)]
    return re.match(r"[^,}\s]*", body[pos:]).group(0)  # type: ignore[union-attr]


def _bib_entries(text: str) -> dict[str, dict[str, str]]:
    """Entries by key, with their fields by lowercase name; each block's body is skipped whole,
    so an `@` inside a value or inside @comment, @preamble and @string blocks starts no entry."""
    entries: dict[str, dict[str, str]] = {}
    pos = 0
    while start := _BIB_START.search(text, pos):
        pos = start.end()
        end = _block_end(text, pos, start.group(2))
        if start.group(1).lower() not in _BIB_NON_ENTRIES and (key := _BIB_KEY.match(text, pos)):
            body = text[key.end() : end]
            fields: dict[str, str] = {}
            at = 0
            while field := _BIB_FIELD.search(body, at):
                value = _bib_value(body, field.end())
                fields.setdefault(field.group(1).lower(), value)
                at = field.end() + len(value) + 1
            entries[key.group(1)] = fields
        pos = end
    return entries


def bibliography(path: str) -> dict[str, dict[str, str]]:
    """Entries of a BibTeX (.bib) or CSL JSON (.json) file by key, with their string fields
    (BibTeX field names lowercased; CSL JSON names as they are, e.g. `DOI`, `title`)."""
    suffix = Path(path).suffix.lower()
    if suffix not in (".bib", ".json"):
        raise ValueError(
            f"Unsupported bibliography file type {suffix!r}: use .bib or .json (CSL JSON)"
        )
    text = _read_text(path)
    if suffix == ".bib":
        return _bib_entries(text)
    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON") from exc
    if not isinstance(items, list):
        raise ValueError(f"{path}: CSL JSON must be a list of items")
    return {
        str(item["id"]): {
            **{k: v for k, v in item.items() if isinstance(v, str)},
            **(
                {"author": _csl_names(item["author"])}
                if isinstance(item.get("author"), list)
                else {}
            ),
        }
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str | int)
    }


def _csl_names(names: list[Any]) -> str:
    """CSL JSON names in BibTeX form, `Family, Given and ...`."""
    return " and ".join(
        ", ".join(str(n[part]) for part in ("family", "given") if part in n)
        if isinstance(n, dict) and "family" in n
        else str(n.get("literal", ""))
        if isinstance(n, dict)
        else ""
        for n in names
    )


def bibliography_keys(path: str) -> set[str]:
    """Entry keys of a BibTeX (.bib) or CSL JSON (.json) file."""
    return set(bibliography(path))


def _anchors(text: str, is_html: bool, rows: list[Row]) -> dict[str, Any]:
    doc = embed._parse(text) if is_html else None
    plain = embed._norm(text)
    checked = 0
    not_found: list[str] = []
    marker_only: list[str] = []
    for label, record in rows:
        anchor = record.get("anchor")
        if not isinstance(anchor, dict):
            continue
        exact = anchor.get("exact")
        if not isinstance(exact, str):
            if "marker" in anchor:
                marker_only.append(label)
            continue
        checked += 1
        needle = embed._norm(exact)
        if doc is not None:
            found = bool(embed._candidates(doc, anchor))
        else:
            found = bool(needle) and needle in plain
        if not found:
            not_found.append(label)
    return {"checked": checked, "not_found": not_found, "marker_only": marker_only}


def _quotes(rows: list[Row], sources: Mapping[str, str]) -> dict[str, list[str]]:
    normalized = {key: ledger.normalize(text) for key, text in sources.items()}
    result: dict[str, list[str]] = {"matched": [], "not_found": [], "no_source": []}
    for label, record in rows:
        quote = record.get("quote")
        if not isinstance(quote, str):
            continue
        key = record.get("key")
        source = normalized.get(key) if isinstance(key, str) else None
        needle = ledger.normalize(quote)
        if source is None:
            result["no_source"].append(label)
        elif needle and needle in source:
            result["matched"].append(label)
        else:
            result["not_found"].append(label)
    return result


def check_ledger(
    path: str,
    work: str | None = None,
    revision: str | None = None,
    bibliography: str | None = None,
    sources: Mapping[str, str] | None = None,
    include_withdrawn: bool = False,
    source_urls: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Check anchors, revisions, quotes and gaps; the result holds ids, keys and counts only."""
    if conflict := sorted(set(sources or {}) & set(source_urls or {})):
        raise ValueError(f"Keys in both sources and source_urls: {', '.join(conflict)}")
    _, all_records = ledger.read(path)
    labelled = [(str(r.get("id", f"record {n}")), r) for n, r in enumerate(all_records, 1)]
    rows = [(label, r) for label, r in labelled if include_withdrawn or "withdrawn" not in r]
    keys = bibliography_keys(bibliography) if bibliography else None
    all_claims: dict[str, list[ledger.Record]] = {}
    for record in all_records:
        if isinstance(record.get("claim_id"), str):
            all_claims.setdefault(record["claim_id"], []).append(record)

    gaps: dict[str, Any] = {
        "missing_evidence": {
            label: missing
            for label, r in rows
            if r.get("contestable", True) and (missing := [f for f in ENTRY_FIELDS if f not in r])
        },
        "claims_without_records": [
            claim for claim, group in all_claims.items() if all("withdrawn" in r for r in group)
        ],
    }
    claims = {r["claim_id"] for _, r in rows if isinstance(r.get("claim_id"), str)}
    result: dict[str, Any] = {"records": len(rows), "claims": len(claims), "gaps": gaps}

    if work is not None:
        text = _read_text(work)
        is_html = Path(work).suffix.lower() in HTML_SUFFIXES
        result["anchors"] = _anchors(text, is_html, rows)
        if keys is None and is_html:
            keys = embed.reference_keys(text) or None
    if keys is not None:
        missing_keys: dict[str, list[str]] = {}
        for label, record in rows:
            if isinstance(record.get("key"), str) and record["key"] not in keys:
                missing_keys.setdefault(record["key"], []).append(label)
        gaps["keys_missing_from_bibliography"] = missing_keys
    if revision is not None:
        different: list[str] = []
        unknown: list[str] = []
        for label, record in rows:
            provenance = record.get("provenance")
            rev = provenance.get("manuscript_rev") if isinstance(provenance, dict) else None
            if rev is None:
                unknown.append(label)
            elif rev != revision:
                different.append(label)
        result["revision"] = {"different": different, "unknown": unknown}
    if sources is not None or source_urls is not None:
        texts = dict(sources or {})
        failed: dict[str, str] = {}
        for key, url in (source_urls or {}).items():
            try:
                texts[key] = fetch.fetch_text(url)
            except fetch.FetchError as exc:
                failed[key] = str(exc)
        result["quotes"] = _quotes(rows, texts)
        if source_urls is not None:
            result["quotes"]["fetch_failed"] = failed
    return result
