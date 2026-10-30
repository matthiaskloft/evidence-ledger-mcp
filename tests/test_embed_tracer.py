"""Tracer bullet for 0.4: embed a ledger in an HTML work over stdio and check the output."""

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
OTHER = {**RECORD, "claim": "A marker-only claim.", "anchor": {"marker": "Section 2"}}
HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Example work</title></head>
<body><main>
<h1>Example work</h1>
<p>Authors who kept a ledger <em>cut unchecked</em> citations from 40 to 3
<span class="citation" data-cites="exampleLedgerStudy2026">(<a
href="#ref-exampleLedgerStudy2026">Example 2026</a>)</span>.</p>
<p>Nothing else is claimed here.</p>
</main>
<div id="refs" class="references">
<div id="ref-exampleLedgerStudy2026">Example, A. (2026). An invented study.</div></div>
</body></html>
"""


async def call(session: ClientSession, tool: str, **arguments: Any) -> Any:
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    return result.structuredContent["result"] if result.structuredContent else None


async def embed(tmp: Path) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "evidence_ledger_mcp"])
    work = tmp / "work.html"
    work.write_text(HTML, "utf-8")
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        path = str(tmp / "ledger.jsonl")
        await call(session, "create_ledger", path=path, work=WORK)
        await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        await call(session, "add_record", path=path, record=OTHER, provenance=PROVENANCE)
        for layout in ("endnotes", "panel"):
            out = str(tmp / f"{layout}.html")
            result = await call(
                session, "embed_ledger", path=path, work=str(work), out=out, layout=layout
            )
            assert (result["layout"], result["claims"], result["located"]) == (layout, 2, 1)
            assert result["not_located"] == ["C-0002"]

            again = {"path": path, "work": str(work), "out": out}
            assert (await session.call_tool("embed_ledger", again)).isError

    assert work.read_text("utf-8") == HTML
    for layout in ("endnotes", "panel"):
        html = (tmp / f"{layout}.html").read_text("utf-8")
        assert 'data-claim="C-0001"' in html and "</mark><sup" in html
        assert '<a href="#ref-exampleLedgerStudy2026">exampleLedgerStudy2026</a>' in html
        assert html.index("Not located in the work") < html.index('id="el-C-0002"')
        assert QUOTE in html
        assert html.count("<style>") == 1
        assert ("<aside" in html and "<script>" in html) == (layout == "panel")
        assert html.count("<h1>Example work</h1>") == 1


def test_embed_over_stdio(tmp_path: Path) -> None:
    anyio.run(embed, tmp_path)
