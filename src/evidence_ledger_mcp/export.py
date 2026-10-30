"""Export a ledger at a level (full, masked, locator) after checking it leaks no extra text."""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from evidence_ledger_mcp import ledger
from evidence_ledger_mcp.ledger import Record
from evidence_ledger_mcp.schema import MAX_EXCERPT_WORDS as MAX_EXCERPT_WORDS
from evidence_ledger_mcp.schema import focus_span

LEVELS = ("full", "masked", "locator")
FORMATS = ("json", "jsonl")
SOURCE_FIELDS = ("quote", "quote_prefix", "quote_suffix", "quote_focus")
# Letters and digits a shared run must reach to count as copied source text.
WINDOW = 24
WORK_FIELDS = ("claim", "anchor")


def mask_quote(quote: str, max_words: int | None = None, focus: str | None = None) -> str:
    """Keep a budgeted focus window or the start and end; default to half at most."""
    words = quote.split()
    if max_words is not None:
        if focus is not None:
            start, end = focus_span(quote, focus)
            if end - start > max_words:
                raise ValueError("quote_focus is longer than max_words")
            spare = max_words - (end - start)
            left = min(start, spare // 2)
            right = min(len(words) - end, spare - left)
            left = min(start, spare - right)
            first, last = start - left, end + right
            return " ".join(
                [
                    *(["…"] if first else []),
                    *words[first:last],
                    *(["…"] if last < len(words) else []),
                ]
            )
        if len(words) <= max_words:
            return " ".join(words)
        start = (max_words + 1) // 2
        end = max_words // 2
        return " ".join([*words[:start], "…", *(words[-end:] if end else [])])
    k = min(3, len(words) // 4)
    if k == 0:
        return "…"
    return " ".join(words[:k]) + " … " + " ".join(words[-k:])


def export_record(record: Record, level: str, max_words: int | None = None) -> Record:
    """Copy a record reduced to the level; `quote_hash` stays at every level."""
    out = copy.deepcopy(record)
    if isinstance(out.get("locator"), dict):
        out["locator"].pop("chunk", None)
    if level == "full":
        return out
    if level == "masked" and isinstance(out.get("quote"), str):
        out["quote"] = (
            mask_quote(out["quote"], max_words, out["quote_focus"])
            if "quote_focus" in out and max_words is not None
            else mask_quote(out["quote"], max_words)
        )
        out.pop("quote_prefix", None)
        out.pop("quote_suffix", None)
        out.pop("quote_focus", None)
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
    header: dict[str, Any],
    exported: list[Record],
    originals: list[Record],
    level: str,
    max_words: int | None = None,
) -> list[str]:
    """Where an export at this level still contains a run of source text from any record."""
    if level == "full":
        return []
    sources = [(str(r.get("id")), _windows(r)) for r in originals]
    problems = []
    if level == "masked":
        by_id = {r.get("id"): r for r in originals}
        for record in exported:
            if "quote" not in record:
                continue
            original = by_id.get(record.get("id"), {}).get("quote")
            masked = record["quote"]
            if not isinstance(original, str) or not isinstance(masked, str):
                problems.append(f"{record.get('id')}: invalid masked quote")
                continue
            budget = max_words if max_words is not None else 2 * min(3, len(original.split()) // 4)
            parts = [part.split() for part in re.split(r"(?<!\S)…(?!\S)", masked) if part.split()]
            source = original.split()
            position = 0
            valid = sum(len(part) for part in parts) <= budget
            for part in parts:
                for index in range(position, len(source) - len(part) + 1):
                    if source[index : index + len(part)] == part:
                        position = index + len(part)
                        break
                else:
                    valid = False
            if not valid:
                problems.append(f"{record.get('id')}: masked quote exceeds budget or source order")
    for label, item in [("header", header), *((str(r.get("id")), r) for r in exported)]:
        # The work's own text is public, and the masked quote is the level's allowance.
        skip = {*WORK_FIELDS, *(["quote"] if level == "masked" and label != "header" else [])}
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
    max_words: int | None = None,
) -> dict[str, Any]:
    """Write the ledger to a new file at the level; refuses if the export leaks source text."""
    if level not in LEVELS:
        raise ValueError(f"level must be one of {', '.join(LEVELS)}")
    if format not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}")
    if max_words is not None:
        if level != "masked":
            raise ValueError("max_words is only allowed with level='masked'")
        if type(max_words) is not int or not 1 <= max_words <= MAX_EXCERPT_WORDS:
            raise ValueError(f"max_words must be an integer from 1 to {MAX_EXCERPT_WORDS}")
    if Path(out).resolve() == Path(path).resolve():
        raise ValueError("out must differ from the ledger file")
    header, records = ledger.read(path)
    header = {**header, "level": level, "max_words": max_words}
    kept = [
        export_record(r, level, max_words)
        for r in records
        if include_withdrawn or "withdrawn" not in r
    ]
    if problems := publication_problems(header, kept, records, level, max_words):
        raise ValueError("Publication check failed: " + "; ".join(problems))
    with open(out, "x", encoding="utf-8", newline="\n") as handle:
        if format == "json":
            doc = {"ledger": header, "records": kept}
            handle.write(json.dumps(doc, ensure_ascii=False, indent=2) + "\n")
        else:
            for obj in [{"ledger": header}, *kept]:
                handle.write(json.dumps(obj, ensure_ascii=False) + "\n")
    return {"path": out, "level": level, "format": format, "records": len(kept)}
