"""Tracer bullet for 0.5: check a ledger over stdio and check what the result holds."""

from __future__ import annotations

import json
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
HTML = (
    "<html><body><p>Keeping a ledger did <em>cut unchecked</em> citations from 40 to 3.</p>"
    '<div id="ref-exampleLedgerStudy2026">Example (2026).</div></body></html>'
)


async def call(session: ClientSession, tool: str, **arguments: Any) -> Any:
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    return result.structuredContent["result"] if result.structuredContent else None


async def checks(tmp: Path) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "evidence_ledger_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        path = str(tmp / "ledger.jsonl")
        work = tmp / "work.html"
        work.write_text(HTML, "utf-8")
        await call(session, "create_ledger", path=path, work=WORK)
        await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        # The server refuses a contestable record without justification, so write it by hand.
        lacking = {
            **RECORD,
            "id": "R-0002",
            "claim_id": "C-0002",
            "key": "missingKey",
            "anchor": {"exact": "not in the work"},
            "quote_hash": "sha256-n2:" + "0" * 64,
            "provenance": {**PROVENANCE, "date": "2026-10-30"},
        }
        del lacking["justification"]
        with open(path, "a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(lacking) + "\n")
        before = Path(path).read_bytes()

        report = await call(
            session,
            "check_ledger",
            path=path,
            work=str(work),
            revision="v2",
            sources={"exampleLedgerStudy2026": f"In year two, {QUOTE}, and so on."},
        )
        assert Path(path).read_bytes() == before

    assert (report["records"], report["claims"]) == (2, 2)
    assert report["gaps"] == {
        "missing_evidence": {"R-0002": ["justification"]},
        "claims_without_records": [],
        "keys_missing_from_bibliography": {"missingKey": ["R-0002"]},
    }
    assert report["anchors"] == {"checked": 2, "not_found": ["R-0002"], "marker_only": []}
    assert report["revision"] == {"different": [], "unknown": ["R-0001", "R-0002"]}
    assert report["quotes"] == {"matched": ["R-0001"], "not_found": [], "no_source": ["R-0002"]}
    assert "unchecked citations" not in json.dumps(report)


def test_check_ledger_over_stdio(tmp_path: Path) -> None:
    anyio.run(checks, tmp_path)
