"""The MCP server: thin tool wrappers around the ledger functions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from evidence_ledger_mcp import embed, export, ledger, summary
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
    provenance date, validates the result and returns the stored record. Mark the phrase
    carrying the claim (a number, term or short statement) with optional `quote_focus`."""
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
    max_words: int | None = None,
) -> Record:
    """Export the ledger to a new file. `masked` keeps the first and last words of each quote,
    `locator` no quoted text; a publication check runs before writing, and `out` is never
    overwritten. `max_words` is allowed only for `masked`, from 1 to 25; None keeps the
    default masking. With a budget, `quote_focus` centres the excerpt. A `full` export
    holds whole quotes: keep it private."""
    return export.export_ledger(path, out, level, format, include_withdrawn, max_words)


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


@mcp.tool()
def embed_ledger(
    path: str,
    work: str,
    out: str,
    level: Literal["full", "masked", "locator"] = "full",
    layout: Literal["endnotes", "panel"] = "endnotes",
    include_withdrawn: bool = False,
) -> Record:
    """Write a copy of the work's HTML (`work`, rendered by Quarto, Pandoc or any tool) with each
    claim's anchor marked and linked to its evidence, to a new file. Both layouts end with an
    "Evidence" section holding one card per claim; `panel` also opens the clicked claim's card in a
    side panel (a bottom sheet on narrow screens); if no anchor is located, `panel` falls back to
    `endnotes` and the result's `layout` says so.
    Anchors that are only a marker, not found in the text or overlapping another claim's marked
    text are listed under "Not located in the work" and returned in `not_located` (`overlapping`
    maps a claim to the one it overlaps); a record key links to `#ref-<key>` when the work has
    that bibliography entry. Levels and the publication check work as in `summarize_ledger`, and
    `out` is never overwritten. A `full` result holds whole quotes: keep it private."""
    return embed.embed_ledger(path, work, out, level, layout, include_withdrawn)


def main() -> None:
    mcp.run()
