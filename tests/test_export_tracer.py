"""Tracer bullet for 0.2: export a ledger at each level over stdio and check what leaves it."""

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
    "locator": {"page": 4, "chunk": {"index": 7, "sha256": "0" * 64}},
    "quote": QUOTE,
    "quote_prefix": "In the second year of the trial,",
    "quote_suffix": "and authors kept the habit afterwards.",
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}


async def call(session: ClientSession, tool: str, **arguments: Any) -> Any:
    result = await session.call_tool(tool, arguments)
    assert not result.isError, result.content
    return result.structuredContent["result"] if result.structuredContent else None


def read_jsonl(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    return lines[0]["ledger"], lines[1:]


async def exports(tmp: Path) -> None:
    params = StdioServerParameters(command=sys.executable, args=["-m", "evidence_ledger_mcp"])
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        path = str(tmp / "ledger.jsonl")
        await call(session, "create_ledger", path=path, work=WORK)
        await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        await call(session, "add_record", path=path, record=RECORD, provenance=PROVENANCE)
        await call(session, "withdraw_record", path=path, id="R-0002", reason="Duplicate")

        for level, fmt in [("full", "jsonl"), ("masked", "json"), ("locator", "jsonl")]:
            out = str(tmp / f"{level}.{fmt}")
            summary = await call(
                session, "export_ledger", path=path, out=out, level=level, format=fmt
            )
            assert (summary["level"], summary["records"]) == (level, 1)

        budget_out = str(tmp / "budget.jsonl")
        await call(session, "export_ledger", path=path, out=budget_out, level="masked", max_words=5)
        budget_header, budget_records = read_jsonl(Path(budget_out))
        assert budget_header["level"] == "masked"
        assert budget_header["max_words"] == 5
        assert budget_records[0]["quote"] == "Ledger records reduced … per manuscript"
        for level in ("full", "locator"):
            failed_budget = await session.call_tool(
                "export_ledger",
                {"path": path, "out": str(tmp / "invalid.jsonl"), "level": level, "max_words": 5},
            )
            assert failed_budget.isError
        assert not (tmp / "invalid.jsonl").exists()

        # An existing file is never overwritten.
        again = {"path": path, "out": str(tmp / "full.jsonl"), "level": "full"}
        assert (await session.call_tool("export_ledger", again)).isError

        # A note quoting the source would leak it: the masked export is refused, nothing written.
        leaky = {**RECORD, "note": f"Says: {QUOTE.upper()}!"}
        await call(session, "add_record", path=path, record=leaky, provenance=PROVENANCE)
        refused = tmp / "refused.jsonl"
        failed = await session.call_tool(
            "export_ledger", {"path": path, "out": str(refused), "level": "masked"}
        )
        assert failed.isError
        assert "R-0003" in str(failed.content)
        assert not refused.exists()

    header, full = read_jsonl(tmp / "full.jsonl")
    assert header["work"] == WORK
    assert [r["id"] for r in full] == ["R-0001"]
    assert full[0]["quote"] == QUOTE
    assert full[0]["quote_prefix"] == RECORD["quote_prefix"]
    assert full[0]["locator"] == {"page": 4}

    masked_doc = json.loads((tmp / "masked.json").read_text("utf-8"))
    assert masked_doc["ledger"]["work"] == WORK
    masked = masked_doc["records"][0]
    assert masked["quote"].startswith("Ledger records")
    assert masked["quote"].endswith("per manuscript")
    assert "unchecked citations from 40" not in masked["quote"]
    assert "quote_prefix" not in masked and "quote_suffix" not in masked
    assert masked["quote_hash"] == full[0]["quote_hash"]

    _, located = read_jsonl(tmp / "locator.jsonl")
    assert not {"quote", "quote_prefix", "quote_suffix"} & located[0].keys()
    assert (located[0]["key"], located[0]["locator"]) == (RECORD["key"], {"page": 4})
    assert located[0]["quote_hash"] == full[0]["quote_hash"]
    assert located[0]["claim"] == RECORD["claim"]


def test_export_levels_over_stdio(tmp_path: Path) -> None:
    anyio.run(exports, tmp_path)
