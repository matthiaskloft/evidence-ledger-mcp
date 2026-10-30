"""The MCP server. A stub for now: it only reports the schema and validates single records."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from evidence_ledger_mcp.schema import record_errors, schema_version

mcp = FastMCP("evidence-ledger")


@mcp.tool()
def schema_info() -> dict[str, str]:
    """Report which evidence ledger schema version this server supports."""
    return {"schema_version": schema_version()}


@mcp.tool()
def validate_record(record: dict[str, Any]) -> list[str]:
    """Validate one ledger record against the schema; returns the violations, empty if valid."""
    return record_errors(record)


def main() -> None:
    mcp.run()
