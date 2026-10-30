"""The MCP server: thin tool wrappers around the ledger functions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from evidence_ledger_mcp import export, ledger, summary
from evidence_ledger_mcp.schema import record_errors, schema_version

mcp = FastMCP(
    "evidence-ledger",
    instructions="Pass ledger paths as absolute paths; relative paths resolve against the "
    "server's working directory.",
)

# Mapping, not dict: FastMCP returns a dict result as is but wraps other types as {"result": ...},
# which keeps every ledger tool's result shape uniform.
Record = Mapping[str, Any]


@mcp.tool()
def schema_info() -> dict[str, str]:
    """Report which evidence ledger schema version this server supports."""
    return {"schema_version": schema_version()}


@mcp.tool()
def validate_record(record: dict[str, Any]) -> list[str]:
    """Validate one ledger record against the schema; returns the violations, empty if valid."""
    return record_errors(record)


@mcp.tool()
def create_ledger(
    path: str, work: dict[str, Any], description: str | None = None, notes: str | None = None
) -> Record:
    """Create a ledger file (JSON Lines) with a header; `work` needs `title` and `type`."""
    return ledger.create_ledger(path, work, description, notes)


@mcp.tool()
def add_record(path: str, record: dict[str, Any], provenance: dict[str, Any]) -> Record:
    """Append a record. The server assigns `id`, `claim_id` (unless given), `quote_hash` and the
    provenance date, validates the result and returns the stored record."""
    return ledger.add_record(path, record, provenance)


@mcp.tool()
def get_record(path: str, id: str) -> Record:
    """Return one record by its id."""
    return ledger.get_record(path, id)


@mcp.tool()
def find_records(
    path: str,
    claim_id: str | None = None,
    key: str | None = None,
    text: str | None = None,
    missing_evidence: bool = False,
    include_withdrawn: bool = False,
) -> list[dict[str, Any]]:
    """Find records by claim_id, source key, text in the claim, or contestable records lacking
    evidence (all filters combine); withdrawn records are left out unless requested."""
    return ledger.find_records(path, claim_id, key, text, missing_evidence, include_withdrawn)


@mcp.tool()
def validate_ledger(path: str) -> list[str]:
    """Validate a whole ledger; returns the problems found, empty if valid."""
    return ledger.validate_ledger(path)


@mcp.tool()
def withdraw_record(path: str, id: str, reason: str) -> Record:
    """Mark a record withdrawn with a reason instead of deleting it."""
    return ledger.withdraw_record(path, id, reason)


@mcp.tool()
def export_ledger(
    path: str,
    out: str,
    level: Literal["full", "masked", "locator"] = "full",
    format: Literal["json", "jsonl"] = "jsonl",
    include_withdrawn: bool = False,
) -> Record:
    """Export the ledger to a new file. `masked` keeps the first and last words of each quote,
    `locator` no quoted text; a publication check runs before writing, and `out` is never
    overwritten. A `full` export holds whole quotes: keep it private."""
    return export.export_ledger(path, out, level, format, include_withdrawn)


@mcp.tool()
def summarize_ledger(
    path: str,
    out: str,
    level: Literal["full", "masked", "locator"] = "full",
    include_withdrawn: bool = False,
) -> Record:
    """Write a standalone HTML summary of the records, grouped by claim, to a new file. Levels
    and the publication check work as in `export_ledger`, and `out` is never overwritten. A
    `full` summary holds whole quotes: keep it private. For a PDF, print the HTML from a
    browser; its print style shows link targets and avoids splitting records where possible."""
    return summary.summarize_ledger(path, out, level, include_withdrawn)


def main() -> None:
    mcp.run()
