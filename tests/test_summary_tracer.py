"""Tracer bullet for 0.3: summarize a ledger over stdio and check the written HTML."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
QUOTE = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
RECORD: dict[str, Any] = {
    "claim": "Keeping a ledger cut unchecked citations from 40 to 3 per manuscript.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "cut unchecked citations from 40 to 3"},
    "key": "exampleLedgerStudy2026",
    "no_identifier_reason": "Invented source for this example",
    "locator": {"page": 4},
    "quote": QUOTE,
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}
OTHER = {**RECORD, "claim": "Authors kept the habit <afterwards>.", "locator": {"section": "5.2"}}


async def call(session: ClientSession, tool: str, **arguments: Any) -> Any:
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    return result.structuredContent["result"] if result.structuredContent else None


async def summarize(tmp: Path) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "evidence_ledger_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        path = str(tmp / "ledger.jsonl")
        await call(session, "create_ledger", path=path, work=WORK)
        await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        await call(session, "add_record", path=path, record=OTHER, provenance=PROVENANCE)
        out = str(tmp / "summary.html")
        result = await call(session, "summarize_ledger", path=path, out=out, level="masked")
        assert (result["level"], result["records"], result["claims"]) == ("masked", 2, 2)

        again = {"path": path, "out": out}
        assert (await session.call_tool("summarize_ledger", again)).isError

    html = (tmp / "summary.html").read_text("utf-8")
    assert "<title>Example work: evidence ledger summary</title>" in html
    assert html.index("C-0001") < html.index("C-0002")
    assert "Authors kept the habit &lt;afterwards&gt;." in html
    assert "page 4" in html and "section 5.2" in html
    assert "Ledger records" in html and "per manuscript" in html
    assert "reduced unchecked" not in html
    assert "<script" not in html


def test_summary_over_stdio(tmp_path: Path) -> None:
    anyio.run(summarize, tmp_path)
