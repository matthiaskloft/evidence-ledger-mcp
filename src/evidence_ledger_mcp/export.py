"""Export a ledger at a level (full, masked, locator) after checking it leaks no extra text."""

from __future__ import annotations

import copy
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evidence_ledger_mcp import ledger
from evidence_ledger_mcp.ledger import Record

LEVELS = ("full", "masked", "locator")
FORMATS = ("json", "jsonl")
SOURCE_FIELDS = ("quote", "quote_prefix", "quote_suffix")
# Letters and digits a shared run must reach to count as copied source text.
WINDOW = 24
WORK_FIELDS = ("claim", "anchor")


def mask_quote(quote: str) -> str:
    """Keep the first and last words of a quote, at most half of its words in total."""
    words = quote.split()
    k = min(3, len(words) // 4)
    if k == 0:
        return "…"
    return " ".join(words[:k]) + " … " + " ".join(words[-k:])


def export_record(record: Record, level: str) -> Record:
    """Copy a record reduced to the level; `quote_hash` stays at every level."""
    out = copy.deepcopy(record)
    if isinstance(out.get("locator"), dict):
        out["locator"].pop("chunk", None)
    if level == "full":
        return out
    if level == "masked" and isinstance(out.get("quote"), str):
        out["quote"] = mask_quote(out["quote"])
        out.pop("quote_prefix", None)
        out.pop("quote_suffix", None)
    else:
        for field in SOURCE_FIELDS:
            out.pop(field, None)
    return out


def _strings(value: object) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _windows(record: Record) -> set[str]:
    """Every WINDOW-character run of the record's normalized source text."""
    runs: set[str] = set()
    for field in SOURCE_FIELDS:
        if isinstance(text := record.get(field), str):
            norm = ledger.normalize(text)
            runs.update(norm[i : i + WINDOW] for i in range(len(norm) - WINDOW + 1))
    return runs


def _leaks(value: object, windows: set[str]) -> bool:
    for text in _strings(value):
        norm = ledger.normalize(text)
        if any(norm[i : i + WINDOW] in windows for i in range(len(norm) - WINDOW + 1)):
            return True
    return False


def publication_problems(
    header: dict[str, Any], exported: list[Record], originals: list[Record], level: str
) -> list[str]:
    """Where an export at this level still contains a run of source text from any record."""
    if level == "full":
        return []
    sources = [(str(r.get("id")), _windows(r)) for r in originals]
    problems = []
    for label, item in [("header", header), *((str(r.get("id")), r) for r in exported)]:
        # The work's own text is public, and the masked quote is the level's allowance.
        skip = {*WORK_FIELDS, *(["quote"] if level == "masked" else [])}
        checked = {k: v for k, v in item.items() if k not in skip}
        problems += [
            f"{label}: contains source text from {source}"
            for source, windows in sources
            if _leaks(checked, windows)
        ]
    return problems


def export_ledger(
    path: str,
    out: str,
    level: str = "full",
    format: str = "jsonl",
    include_withdrawn: bool = False,
) -> dict[str, Any]:
    """Write the ledger to a new file at the level; refuses if the export leaks source text."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {', '.join(LEVELS)}")
    if format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    if Path(out).resolve() == Path(path).resolve():
        raise ValueError("out must differ from the ledger file")
    header, records = ledger.read(path)
    kept = [export_record(r, level) for r in records if include_withdrawn or "withdrawn" not in r]
    if problems := publication_problems(header, kept, records, level):
        raise ValueError("Publication check failed: " + "; ".join(problems))
    with open(out, "x", encoding="utf-8", newline="\n") as handle:
        if format == "json":
            doc = {"ledger": header, "records": kept}
            handle.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        else:
            for obj in [{"ledger": header}, *kept]:
                handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return {"path": out, "level": level, "format": format, "records": len(kept)}
