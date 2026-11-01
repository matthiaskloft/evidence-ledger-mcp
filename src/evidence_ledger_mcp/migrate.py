"""Import an older ledger (YAML, JSON or JSON Lines; any schema version or none)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from evidence_ledger_mcp.ledger import (
    Record,
    _next_number,
    _rewrite,
    quote_hash,
    validate_ledger,
)
from evidence_ledger_mcp.schema import header_errors, schema_version


def _plain(value: Any) -> Any:
    """Turn the dates and datetimes YAML parses from unquoted values back into ISO strings."""
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_plain(v) for v in value]
    return value


def _jsonl(text: str, source: str) -> Any:
    """Read JSON Lines: a `{"ledger": ...}` header on the first line, then one record per line."""
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {number} is not valid JSON")
            continue
        if not isinstance(item, dict):
            errors.append(f"line {number} is not an object")
            continue
        items.append(item)
    if errors:
        raise ValueError(f"{source}: " + "; ".join(errors))
    if items and set(items[0]) == {"ledger"} and isinstance(items[0]["ledger"], dict):
        return {"ledger": items[0]["ledger"], "records": items[1:]}
    return items


def _starts_with_header(text: str) -> bool:
    first = next((line for line in text.splitlines() if line.strip()), "")
    try:
        item = json.loads(first)
    except json.JSONDecodeError:
        return False
    return isinstance(item, dict) and set(item) == {"ledger"}


def _load(source: str) -> Any:
    text = Path(source).read_text("utf-8-sig")
    suffix = Path(source).suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            return _plain(yaml.safe_load(text))
        except yaml.YAMLError as exc:
            raise ValueError(f"{source} is not valid YAML") from exc
    if suffix == ".jsonl" or _starts_with_header(text):
        return _jsonl(text, source)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} is not valid JSON") from exc


Header = dict[str, Any]
Records = list[dict[str, Any]]
Step = tuple[str, str, Callable[[Header, Records], tuple[Header, Records]]]


def _unchanged(header: Header, records: Records) -> tuple[Header, Records]:
    return header, records


# Ordered upgrade steps. 0.2.0 to 0.3.0 added the header and the optional `note`; 0.3.0 to 0.4.0
# added `quote_focus`, the n2 hash (n1 hashes stay checkable) and the export header fields. All
# are additions, so no record changes. A pre-schema list starts at the first step.
STEPS: list[Step] = [
    ("0.2.0", "0.3.0", _unchanged),
    ("0.3.0", "0.4.0", _unchanged),
]


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _upgrade(header: Header, records: Records) -> tuple[Header, Records, str | None, list[str]]:
    """Apply the steps from the header's schema version up to the server's."""
    target = schema_version()
    known = [STEPS[0][0], *(to for _, to, _ in STEPS)]
    source_version = header.get("schema_version")
    if source_version is None:
        start = 0
    else:
        if not isinstance(source_version, str) or source_version not in known:
            if (
                isinstance(source_version, str)
                and source_version.count(".") == 2
                and all(part.isdigit() for part in source_version.split("."))
                and _version_key(source_version) > _version_key(target)
            ):
                raise ValueError(
                    f"The source follows schema {source_version}, newer than this server's {target}"
                )
            raise ValueError(
                f"Unknown schema_version {source_version!r}; known versions: " + ", ".join(known)
            )
        start = known.index(source_version)
    steps: list[str] = []
    for from_version, to_version, step in STEPS[start:]:
        header, records = step(header, records)
        steps.append(f"{from_version}→{to_version}")
        if to_version == target:
            break
    return header, records, source_version, steps


def import_ledger(source: str, path: str, work: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write the ledger in `source` to a new JSON Lines file `path` and validate the result.

    The source version comes from its header (`from_version` is None for a pre-schema list or a
    header without one); the upgrade steps up to this server's version are listed in `steps`.
    """
    if Path(source).resolve() == Path(path).resolve():
        raise ValueError("path must differ from source")
    if Path(path).exists():
        raise ValueError(f"{path} already exists and is not overwritten")
    data = _load(source)
    if isinstance(data, list):
        if work is None:
            raise ValueError("A plain list of records has no header: pass `work`")
        header: dict[str, Any] = {"work": work}
        records = data
    elif isinstance(data, dict) and isinstance(data.get("ledger"), dict):
        if work is not None:
            raise ValueError("The source has a header: do not pass `work`")
        header = dict(data["ledger"])
        records = data.get("records", [])
    else:
        raise ValueError("Expected a list of records or an object with `ledger` and `records`")
    if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
        raise ValueError("`records` must be a list of records")

    records = [dict(r) for r in records]
    header, records, from_version, steps = _upgrade(header, records)
    header["schema_version"] = schema_version()
    header.setdefault("created", date.today().isoformat())
    if errors := header_errors(header):
        raise ValueError("Invalid header: " + "; ".join(errors))

    imported: list[Record] = records
    ids = [str(r["id"]) for r in imported if "id" in r]
    claim_ids = [str(r["claim_id"]) for r in imported if "claim_id" in r]
    for record in imported:
        if "id" not in record:
            record["id"] = _next_number(ids, "R")
            ids.append(record["id"])
        if "claim_id" not in record:
            record["claim_id"] = _next_number(claim_ids, "C")
            claim_ids.append(record["claim_id"])
        if isinstance(record.get("quote"), str) and "quote_hash" not in record:
            record["quote_hash"] = quote_hash(record["quote"])

    _rewrite(path, header, imported)
    return {
        "path": path,
        "records": len(imported),
        "from_version": from_version,
        "steps": steps,
        "problems": validate_ledger(path),
    }
