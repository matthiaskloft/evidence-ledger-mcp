"""Tracer bullet for link resolution: an author embeds a ledger in the work, a co-author relinks
the received HTML to their own copy of the PDF, all over stdio. Reading a PDF inside the running
server once hung on Windows, so this runs offline on every test run."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from test_links import make_pdf

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
QUOTE = "It can be proven that most claimed research findings are false."
PDF = make_pdf(
    ["Why most published research findings are false", "doi: 10.1371/journal.pmed.0020124"],
    ["Essay", QUOTE],
)
RECORD: dict[str, Any] = {
    "claim": "Most published findings may be false.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "may be false"},
    "key": "ioannidis2005",
    "doi": "10.1371/journal.pmed.0020124",
    "locator": {"page": 696},
    "quote": QUOTE,
    "relation": "supports",
    "justification": "The essay states it outright.",
    "retrieved_via": "pdf",
}
HTML = (
    "<html><head><title>Work</title></head><body><p>Most findings may be false.</p></body></html>"
)


async def call(session: ClientSession, tool: str, **arguments: Any) -> Any:
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    return result.structuredContent["result"] if result.structuredContent else None


async def relink(tmp: Path) -> None:
    author, coauthor = tmp / "author", tmp / "coauthor"
    author.mkdir()
    (coauthor / "papers").mkdir(parents=True)
    (coauthor / "papers" / "Why most published research findings are false.pdf").write_bytes(PDF)
    (author / "work.html").write_text(HTML, "utf-8")
    params = StdioServerParameters(command=sys.executable, args=["-m", "evidence_ledger_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        path = str(author / "ledger.jsonl")
        await call(session, "create_ledger", path=path, work=WORK)
        await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        out = author / "work.embedded.html"
        await call(
            session,
            "embed_ledger",
            path=path,
            work=str(author / "work.html"),
            out=str(out),
            level="masked",
        )

        received = coauthor / "work.embedded.html"
        shutil.copy(out, received)  # the co-author has the HTML and their PDFs, not the ledger
        result = await call(
            session, "relink_html", html=str(received), folder=str(coauthor / "papers")
        )
        assert result["found"] == ["R-0001"] and "Do not share" in result["notice"]

        bad = {"path": path, "folder": str(coauthor / "papers"), "link_file": str(tmp / "l.json")}
        assert (await session.call_tool("resolve_links", bad)).isError

    html = (coauthor / "work.embedded.private.html").read_text("utf-8")
    assert "<title>[Private] Work</title>" in html and "Do not share" in html
    assert "papers/Why%20most%20published%20research%20findings%20are%20false.pdf#page=2" in html
    assert "Your copy" not in received.read_text("utf-8")


def test_relink_over_stdio(tmp_path: Path) -> None:
    anyio.run(relink, tmp_path)
