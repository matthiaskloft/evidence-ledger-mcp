"""Check a ledger against its work, bibliography and sources; reports ids, keys and counts only."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evidence_ledger_mcp import embed, ledger

HTML_SUFFIXES = (".html", ".htm")
ENTRY_FIELDS = ("locator", "quote", "justification")
_BIB_START = re.compile(r"^\s*@\s*(\w+)\s*([{(])", re.M)
_BIB_KEY = re.compile(r"\s*([^,\s]+)\s*,")
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


def _bib_keys(text: str) -> set[str]:
    """Entry keys, skipping the whole body of @comment, @preamble and @string blocks."""
    keys: set[str] = set()
    pos = 0
    while start := _BIB_START.search(text, pos):
        pos = start.end()
        if start.group(1).lower() in _BIB_NON_ENTRIES:
            pos = _block_end(text, pos, start.group(2))
        elif key := _BIB_KEY.match(text, pos):
            keys.add(key.group(1))
    return keys


def bibliography_keys(path: str) -> set[str]:
    """Entry keys of a BibTeX (.bib) or CSL JSON (.json) file."""
    suffix = Path(path).suffix.lower()
    if suffix not in (".bib", ".json"):
        raise ValueError(
            f"Unsupported bibliography file type {suffix!r}: use .bib or .json (CSL JSON)"
        )
    text = _read_text(path)
    if suffix == ".bib":
        return _bib_keys(text)
    try:
        items = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: not valid JSON") from exc
    if not isinstance(items, list):
        raise ValueError(f"{path}: CSL JSON must be a list of items")
    return {
        str(item["id"])
        for item in items
        if isinstance(item, dict) and isinstance(item.get("id"), str | int)
    }


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
) -> dict[str, Any]:
    """Check anchors, revisions, quotes and gaps; the result holds ids, keys and counts only."""
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
    if sources is not None:
        result["quotes"] = _quotes(rows, sources)
    return result
