"""Read and write evidence ledgers stored as JSON Lines: a header line, then one record per line."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from evidence_ledger_mcp.schema import header_errors, record_errors, schema_version

Record = dict[str, Any]
EVIDENCE_FIELDS = ("locator", "quote", "quote_hash", "justification")


def quote_hash(quote: str) -> str:
    """Hash a quote after normalization n1: NFKC, casefold, keep only letters and digits."""
    folded = unicodedata.normalize("NFKC", quote).casefold()
    kept = "".join(c for c in folded if unicodedata.category(c)[0] in "LN")
    return "sha256-n1:" + hashlib.sha256(kept.encode("utf-8")).hexdigest()


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


def _read(path: str) -> tuple[dict[str, Any], list[Record]]:
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


def add_record(path: str, record: Record, provenance: dict[str, Any]) -> Record:
    """Complete a record (id, claim_id, quote_hash, provenance date), validate and append it."""
    for field in ("id", "withdrawn"):
        if field in record:
            raise ValueError(f"'{field}' is assigned by the server and cannot be supplied")
    _, existing = _read(path)
    new: Record = {"id": _next_number([str(r.get("id", "")) for r in existing], "R"), **record}
    new.setdefault("claim_id", _next_number([str(r.get("claim_id", "")) for r in existing], "C"))
    if "quote" in new:
        new["quote_hash"] = quote_hash(new["quote"])
    elif "quote_hash" in new:
        raise ValueError("'quote_hash' without 'quote' cannot be checked")
    new["provenance"] = {**provenance, "date": date.today().isoformat()}
    if errors := record_errors(new):
        raise ValueError("Invalid record: " + "; ".join(errors))
    for other in existing:
        same_claim = other.get("claim_id") == new["claim_id"]
        if same_claim and other.get("importance") != new.get("importance"):
            raise ValueError(f"importance differs from {other.get('id')} on {new['claim_id']}")
    # A hand-edited file may lack its final newline; appending would join two lines.
    prefix = "" if Path(path).read_bytes().endswith(b"\n") else "\n"
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(prefix + _dumps(new) + "\n")
    return new


def get_record(path: str, id: str) -> Record:
    """Return the record with this id."""
    for record in _read(path)[1]:
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
    for record in _read(path)[1]:
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
    seen_ids: set[str] = set()
    importance: dict[str, set[str | None]] = {}
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
        problems += [f"{label}: {e}" for e in record_errors(record)]
        if label in seen_ids:
            problems.append(f"{label}: duplicate id (line {number})")
        seen_ids.add(label)
        quote = record.get("quote")
        if (
            isinstance(quote, str)
            and "quote_hash" in record
            and record["quote_hash"] != (quote_hash(quote))
        ):
            problems.append(f"{label}: quote_hash does not match quote")
        # A non-string importance is already reported above and cannot go into a set.
        if "claim_id" in record and isinstance(record.get("importance"), str | None):
            importance.setdefault(str(record["claim_id"]), set()).add(record.get("importance"))
    problems += [
        f"{claim}: records disagree on importance"
        for claim, levels in importance.items()
        if len(levels) > 1
    ]
    return problems


def withdraw_record(path: str, id: str, reason: str) -> Record:
    """Mark a record withdrawn with a reason; the record stays in the file."""
    header, records = _read(path)
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
