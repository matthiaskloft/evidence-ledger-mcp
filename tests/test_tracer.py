"""Tracer bullet for 0.1: drive the real server over stdio through the whole ledger lifecycle."""

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
# The schema README's minimal record, minus the fields the server fills in.
RECORD: dict[str, Any] = {
    "claim": "Keeping a ledger cut unchecked citations from 40 to 3 per manuscript.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "cut unchecked citations from 40 to 3"},
    "key": "exampleLedgerStudy2026",
    "no_identifier_reason": "Invented source for this example",
    "locator": {"page": 4},
    "quote": "Ledger records reduced unchecked citations from 40 to 3 per manuscript",
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}
README_HASH = "sha256-n2:3b8d67a25018dccc865ee88b24c10aa4a5b553e41ff28ebc46936a71eee7db3c"


async def call(session: ClientSession, tool: str, **arguments: Any) -> Any:
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    return result.structuredContent["result"] if result.structuredContent else None


async def lifecycle(ledger: Path) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "evidence_ledger_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        path = str(ledger)

        await call(session, "create_ledger", path=path, work=WORK)
        first = await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        assert first["id"] == "R-0001"
        assert first["claim_id"] == "C-0001"
        assert first["quote_hash"] == README_HASH
        assert first["provenance"]["date"]

        # A second source for the same claim keeps its claim_id.
        second = await call(
            session,
            "add_record",
            path=path,
            record={**RECORD, "key": "otherStudy2025", "claim_id": "C-0001"},
            provenance=PROVENANCE,
        )
        assert (second["id"], second["claim_id"]) == ("R-0002", "C-0001")

        by_key = await call(session, "find_records", path=path, key="otherStudy2025")
        assert [r["id"] for r in by_key] == ["R-0002"]
        assert (await call(session, "get_record", path=path, id="R-0001"))["key"] == RECORD["key"]

        edited = await call(
            session,
            "update_record",
            path=path,
            id="R-0002",
            changes={"claim": "Keeping a ledger cut unchecked citations a lot.", "note": None},
        )
        assert edited["id"] == "R-0002"
        assert edited["provenance"] == second["provenance"]
        batch = await call(
            session,
            "update_records",
            path=path,
            updates=[{"id": "R-0001", "changes": {"locator": {"page": 3}}}],
        )
        assert batch[0]["locator"] == {"page": 3}
        assert (await call(session, "get_record", path=path, id="R-0001"))["claim"] == (
            edited["claim"]
        )
        failed = await session.call_tool(
            "update_record",
            {"path": path, "id": "R-0002", "changes": {"id": "R-0009"}},
        )
        assert failed.isError
        failed = await session.call_tool(
            "update_records", {"path": path, "updates": [{"id": "R-0009", "changes": {"a": 1}}]}
        )
        assert failed.isError

        await call(session, "withdraw_record", path=path, id="R-0002", reason="Duplicate")
        active = await call(session, "find_records", path=path, claim_id="C-0001")
        assert [r["id"] for r in active] == ["R-0001"]
        assert await call(session, "validate_ledger", path=path) == []

        # Errors reach the client as error results, and nothing is written.
        failed = await session.call_tool("get_record", {"path": path, "id": "R-9999"})
        assert failed.isError
        failed = await session.call_tool("create_ledger", {"path": path, "work": WORK})
        assert failed.isError

    lines = [json.loads(line) for line in ledger.read_text("utf-8").splitlines()]
    assert lines[0]["ledger"]["work"] == WORK
    assert [line["id"] for line in lines[1:]] == ["R-0001", "R-0002"]
    assert lines[2]["withdrawn"] == "Duplicate"


def test_ledger_lifecycle_over_stdio(tmp_path: Path) -> None:
    anyio.run(lifecycle, tmp_path / "ledger.jsonl")


def test_server_instructions_point_to_bug_report_and_require_review_before_filing() -> None:
    from evidence_ledger_mcp.server import mcp

    text = mcp.instructions or ""
    assert "template=bug_report.yml" in text
    for phrase in (
        "stop and tell the user",
        "edit the ledger by hand",
        "only after the user has reviewed the full draft",
        "never file or comment without that approval",
        "search the open and closed issues",
        "invented record",
        "never real quotes, claims, justifications or work titles",
        "absolute paths, usernames and credentials",
        "schema_info",
        "exact error text",
        "not a server bug",
    ):
        assert phrase in text


def test_server_instructions_state_the_working_directory_note_once() -> None:
    from evidence_ledger_mcp.server import mcp

    assert (mcp.instructions or "").count("server's working directory") == 1
