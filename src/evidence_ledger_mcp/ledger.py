"""Read and write evidence ledgers stored as JSON Lines: a header line, then one record per line."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

from evidence_ledger_mcp.schema import header_errors, record_errors, schema_version

Record = dict[str, Any]
EVIDENCE_FIELDS = ("locator", "quote", "quote_hash", "justification")
# Fields every record of a claim shares.
CLAIM_FIELDS = ("claim", "importance")


def normalize(text: str, version: str = "n2") -> str:
    """Normalize with n2 (or legacy n1), keeping only letters and digits."""
    if version not in ("n1", "n2"):
        raise ValueError(f"Unsupported quote hash normalization: {version}")
    folded = unicodedata.normalize("NFKC", text).casefold()
    if version == "n2":
        folded = unicodedata.normalize("NFKC", folded)
    return "".join(c for c in folded if unicodedata.category(c)[0] in "LN")


def quote_hash(quote: str, version: str = "n2") -> str:
    """Hash a quote with n2 by default; n1 remains available for verification."""
    return (
        f"sha256-{version}:" + hashlib.sha256(normalize(quote, version).encode("utf-8")).hexdigest()
    )


SOURCE_FIELDS = ("quote", "quote_prefix", "quote_suffix", "quote_focus")
# Fields that quote the work itself, which is public; every other field is exported at all levels.
WORK_FIELDS = ("claim", "anchor")
# Letters and digits a shared run must reach to count as copied source text.
WINDOW = 24


def _strings(value: object, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for name, item in value.items():
            yield from _strings(item, f"{path}.{name}" if path else str(name))
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item, path)


def windows(record: Record) -> set[str]:
    """Every WINDOW-character run of the record's normalized source text."""
    runs: set[str] = set()
    for field in SOURCE_FIELDS:
        if isinstance(text := record.get(field), str):
            norm = normalize(text)
            runs.update(norm[i : i + WINDOW] for i in range(len(norm) - WINDOW + 1))
    return runs


def leaks(value: object, runs: set[str]) -> bool:
    """Whether any string in value shares a WINDOW-character run with the source text."""
    for _, text in _strings(value):
        norm = normalize(text)
        if any(norm[i : i + WINDOW] in runs for i in range(len(norm) - WINDOW + 1)):
            return True
    return False


def source_overlaps(record: Record) -> list[str]:
    """Fields outside the quote fields that repeat a run of the record's own source text."""
    runs = windows(record)
    found = []
    for field, value in record.items():
        if field in SOURCE_FIELDS or field in WORK_FIELDS or field == "quote_hash":
            continue
        for path, text in _strings(value, field):
            norm = normalize(text)
            starts = [i for i in range(len(norm) - WINDOW + 1) if norm[i : i + WINDOW] in runs]
            if starts:
                end = starts[0] + WINDOW
                while end < len(norm) and norm[end - WINDOW + 1 : end + 1] in runs:
                    end += 1
                run = norm[starts[0] : end]
                found.append(f"{path} repeats source text (letters and digits only: '{run}')")
    return found


def _dumps(obj: object) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _lines(path: str) -> list[str]:
    # Split on "\n" only: raw U+2028, U+2029 and U+0085 inside JSON strings are not line breaks.
    return Path(path).read_text("utf-8-sig").removesuffix("\n").split("\n")


def _header(line: str) -> dict[str, Any] | None:
    try:
        header = json.loads(line)["ledger"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    return header if isinstance(header, dict) else None


def read(path: str) -> tuple[dict[str, Any], list[Record]]:
    """Parse a ledger strictly; raises ValueError naming the line that cannot be read."""
    lines = _lines(path)
    header = _header(lines[0]) if lines else None
    if header is None:
        raise ValueError(f"{path}: line 1 is not a ledger header")
    records: list[Record] = []
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: line {number} is not valid JSON") from exc
        if not isinstance(record, dict):
            raise ValueError(f"{path}: line {number} is not a record")
        records.append(record)
    return header, records


def _next_number(values: list[str], prefix: str) -> str:
    numbers = [int(m[1]) for v in values if (m := re.fullmatch(rf"{prefix}-(\d+)", v))]
    return f"{prefix}-{max(numbers, default=0) + 1:04d}"


def _rewrite(path: str, header: dict[str, Any], records: list[Record]) -> None:
    """Replace the file atomically: write a temp file in the same directory, then swap it in."""
    text = "".join(_dumps(obj) + "\n" for obj in [{"ledger": header}, *records])
    fd, tmp = tempfile.mkstemp(dir=Path(path).parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def create_ledger(
    path: str, work: dict[str, Any], description: str | None = None, notes: str | None = None
) -> dict[str, Any]:
    """Create a new ledger file with a header; refuses to overwrite an existing file."""
    header: dict[str, Any] = {
        "schema_version": schema_version(),
        "work": work,
        "created": date.today().isoformat(),
    }
    if description is not None:
        header["description"] = description
    if notes is not None:
        header["notes"] = notes
    if errors := header_errors(header):
        raise ValueError("Invalid header: " + "; ".join(errors))
    with open(path, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(_dumps({"ledger": header}) + "\n")
    return header


def _check(header: dict[str, Any], record: Record, others: list[Record]) -> None:
    """Raise ValueError if the record breaks the schema, repeats its source text outside the
    quote fields, or disagrees with another record of its claim."""
    if errors := record_errors(record):
        raise ValueError("Invalid record: " + "; ".join(errors))
    runs = windows(record)
    overlaps = source_overlaps(record)
    overlaps += [
        f"header.{field} repeats source text"
        for field in ("description", "notes")
        if leaks(header.get(field), runs)
    ]
    if overlaps:
        raise ValueError(
            "Source text outside the quote fields: "
            + "; ".join(overlaps)
            + ". This is a rule, not a server error: rewrite the field in your own words; "
            f"{WINDOW} or more letters and digits of the quote would block a masked or locator "
            "export."
        )
    for other in others:
        if other.get("claim_id") != record.get("claim_id"):
            continue
        for field in CLAIM_FIELDS:
            if other.get(field) != record.get(field):
                raise ValueError(f"{field} differs from {other.get('id')} on {record['claim_id']}")


def add_record(path: str, record: Record, provenance: dict[str, Any]) -> Record:
    """Complete a record (id, claim_id, quote_hash, provenance date), validate and append it."""
    for field in ("id", "withdrawn"):
        if field in record:
            raise ValueError(f"'{field}' is assigned by the server and cannot be supplied")
    header, existing = read(path)
    new: Record = {"id": _next_number([str(r.get("id", "")) for r in existing], "R"), **record}
    new.setdefault("claim_id", _next_number([str(r.get("claim_id", "")) for r in existing], "C"))
    if "quote" in new:
        new["quote_hash"] = quote_hash(new["quote"])
    elif "quote_hash" in new:
        raise ValueError("'quote_hash' without 'quote' cannot be checked")
    new["provenance"] = {**provenance, "date": date.today().isoformat()}
    _check(header, new, existing)
    # A hand-edited file may lack its final newline; appending would join two lines.
    prefix = "" if Path(path).read_bytes().endswith(b"\n") else "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + _dumps(new) + "\n")
    return new


def update_records(path: str, updates: list[dict[str, Any]]) -> list[Record]:
    """Apply `updates` (each `{"id": ..., "changes": {...}}`) in order and rewrite the ledger once.

    Each change is merged into the record (None removes a field) and refreshes its quote hash;
    `claim` or `importance` changes are copied to the other records of the claim. The record's
    provenance stays as it was: it records the original assessment. Later updates see earlier
    ones, a duplicate id is applied in order, and every affected record is checked against the
    final state. All refusals are collected into one ValueError, each prefixed with the item
    index and record id, and nothing is written then. Returns, for each item, its record in the
    final state (so two items on one record return the same, fully updated record)."""
    return _update(path, updates, single=False)


def _update(path: str, updates: list[dict[str, Any]], single: bool) -> list[Record]:
    """Core of `update_records`; `single` drops the batch prefixes from the error message."""
    if not updates:
        raise ValueError("No updates given")
    header, records = read(path)
    errors: list[str] = []
    touched: dict[str, int] = {}  # record id -> index of the last update that changed it
    applied: list[str | None] = []
    for index, item in enumerate(updates):
        prefix = "" if single else f"updates[{index}] ({item.get('id')}): "
        applied.append(None)
        id, changes = item.get("id"), item.get("changes")
        if not isinstance(id, str) or not isinstance(changes, dict):
            errors.append(prefix + "needs an 'id' string and a 'changes' object")
            continue
        forbidden = [f for f in ("id", "withdrawn", "quote_hash", "provenance") if f in changes]
        if forbidden:
            errors.append(prefix + f"{', '.join(repr(f) for f in forbidden)} cannot be changed")
            continue
        if not changes:
            errors.append(prefix + "No changes given")
            continue
        position = next((n for n, r in enumerate(records) if r.get("id") == id), None)
        if position is None:
            errors.append(prefix + f"No record {id} in {path}")
            continue
        target = records[position]
        if "withdrawn" in target:
            errors.append(prefix + f"{id} is withdrawn and cannot be changed")
            continue
        updated: Record = {k: v for k, v in target.items() if k not in changes}
        updated.update({k: v for k, v in changes.items() if v is not None})
        if "quote" in changes:
            if "quote" not in updated:
                updated.pop("quote_hash", None)
            elif updated["quote"] != target.get("quote"):
                updated["quote_hash"] = quote_hash(updated["quote"])
        records[position] = updated
        touched[id] = index
        applied[index] = id
        if claim_changes := {f: changes[f] for f in CLAIM_FIELDS if f in changes}:
            for number, other in enumerate(records):
                if number != position and other.get("claim_id") == updated.get("claim_id"):
                    records[number] = {k: v for k, v in other.items() if k not in claim_changes} | {
                        k: v for k, v in claim_changes.items() if v is not None
                    }
                    touched[str(other.get("id"))] = index
    for id, index in touched.items():
        record = next(r for r in records if r.get("id") == id)
        try:
            _check(header, record, [r for r in records if r is not record])
        except ValueError as error:
            errors.append(str(error) if single else f"updates[{index}] ({id}): {error}")
    if errors:
        if single:
            raise ValueError(errors[0])
        raise ValueError(f"{len(errors)} problem(s), nothing written: " + " | ".join(errors))
    _rewrite(path, header, records)
    by_id = {str(r.get("id")): r for r in records}
    return [by_id[str(id)] for id in applied]


def update_record(path: str, id: str, changes: Record) -> Record:
    """Merge `changes` into one record and return it; see `update_records`."""
    return _update(path, [{"id": id, "changes": changes}], single=True)[0]


def get_record(path: str, id: str) -> Record:
    """Return the record with this id."""
    for record in read(path)[1]:
        if record.get("id") == id:
            return record
    raise ValueError(f"No record {id} in {path}")


def find_records(
    path: str,
    claim_id: str | None = None,
    key: str | None = None,
    text: str | None = None,
    missing_evidence: bool = False,
    include_withdrawn: bool = False,
) -> list[Record]:
    """Records matching all given filters; withdrawn ones only with `include_withdrawn`."""
    found = []
    for record in read(path)[1]:
        if "withdrawn" in record and not include_withdrawn:
            continue
        if claim_id is not None and record.get("claim_id") != claim_id:
            continue
        if key is not None and record.get("key") != key:
            continue
        if text is not None and text.casefold() not in str(record.get("claim", "")).casefold():
            continue
        if missing_evidence and (
            not record.get("contestable", True) or all(f in record for f in EVIDENCE_FIELDS)
        ):
            continue
        found.append(record)
    return found


def validate_ledger(path: str) -> list[str]:
    """Return all problems found in the ledger, empty if it is valid."""
    lines = _lines(path)
    header = _header(lines[0]) if lines else None
    if header is None:
        return ["line 1: not a ledger header"]
    problems = [f"header: {e}" for e in header_errors(header)]
    if header.get("schema_version") != schema_version():
        problems.append(
            f"header: schema_version {header.get('schema_version')} "
            f"differs from the server's {schema_version()}"
        )
    from evidence_ledger_mcp.export import export_level_problems  # export imports this module

    level = header.get("level")
    seen_ids: set[str] = set()
    importance: dict[str, set[str | None]] = {}
    claims: dict[str, set[str]] = {}
    for number, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"line {number}: not valid JSON")
            continue
        if not isinstance(record, dict):
            problems.append(f"line {number}: not a record")
            continue
        label = str(record.get("id", f"line {number}"))
        # A locator export drops `quote`, which the record schema requires for contestable
        # records; a placeholder lets the rest of the schema apply, and the level's own
        # checks report any source text left in the record.
        checked = (
            {**record, "quote": "…"} if level == "locator" and "quote" not in record else record
        )
        problems += [f"{label}: {e}" for e in record_errors(checked)]
        problems += [f"{label}: {e}" for e in source_overlaps(record)]
        runs = windows(record)
        problems += [
            f"{label}: header.{field} repeats source text"
            for field in ("description", "notes")
            if leaks(header.get(field), runs)
        ]
        if level in ("masked", "locator"):
            problems += [
                f"{label}: {e}"
                for e in export_level_problems(record, level, header.get("max_words"))
            ]
        if label in seen_ids:
            problems.append(f"{label}: duplicate id (line {number})")
        seen_ids.add(label)
        quote = record.get("quote")
        if (
            level != "masked"  # a masked quote cannot reproduce the hash of the full quote
            and isinstance(quote, str)
            and "quote_hash" in record
            and (
                not isinstance(record["quote_hash"], str)
                or record["quote_hash"].split(":")[0] not in ("sha256-n1", "sha256-n2")
                or record["quote_hash"]
                != quote_hash(quote, record["quote_hash"].split(":")[0].removeprefix("sha256-"))
            )
        ):
            problems.append(f"{label}: quote_hash does not match quote")
        # A non-string importance is already reported above and cannot go into a set.
        if "claim_id" in record and isinstance(record.get("importance"), str | None):
            importance.setdefault(str(record["claim_id"]), set()).add(record.get("importance"))
        if "claim_id" in record and isinstance(record.get("claim"), str):
            claims.setdefault(str(record["claim_id"]), set()).add(record["claim"])
    problems += [
        f"{claim}: records disagree on importance"
        for claim, levels in importance.items()
        if len(levels) > 1
    ]
    problems += [
        f"{claim}: records disagree on claim text"
        for claim, texts in claims.items()
        if len(texts) > 1
    ]
    return problems


def withdraw_record(path: str, id: str, reason: str) -> Record:
    """Mark a record withdrawn with a reason; the record stays in the file."""
    header, records = read(path)
    for record in records:
        if record.get("id") == id:
            if "withdrawn" in record:
                raise ValueError(f"{id} is already withdrawn")
            if not reason.strip():
                raise ValueError("A withdrawal needs a reason")
            record["withdrawn"] = reason
            _rewrite(path, header, records)
            return record
    raise ValueError(f"No record {id} in {path}")
