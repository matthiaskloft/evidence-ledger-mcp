"""Import an older ledger (YAML or JSON, schema 0.2 to 0.4) as a JSON Lines ledger."""

from __future__ import annotations

import json
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


def _load(source: str) -> Any:
    text = Path(source).read_text("utf-8-sig")
    if Path(source).suffix.lower() in (".yaml", ".yml"):
        try:
            return _plain(yaml.safe_load(text))
        except yaml.YAMLError as exc:
            raise ValueError(f"{source} is not valid YAML") from exc
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} is not valid JSON") from exc


def import_ledger(source: str, path: str, work: dict[str, Any] | None = None) -> dict[str, Any]:
    """Write the ledger in `source` to a new JSON Lines file `path` and validate the result."""
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

    header["schema_version"] = schema_version()
    header.setdefault("created", date.today().isoformat())
    if errors := header_errors(header):
        raise ValueError("Invalid header: " + "; ".join(errors))

    imported: list[Record] = [dict(r) for r in records]
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
    return {"path": path, "records": len(imported), "problems": validate_ledger(path)}
