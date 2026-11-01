from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import ledger
from evidence_ledger_mcp.migrate import import_ledger
from evidence_ledger_mcp.schema import schema_version

PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
WORK = {"title": "Example work", "type": "manuscript"}
QUOTE = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
N1_HASH = ledger.quote_hash(QUOTE, "n1")


def record(number: int, claim: int, **extra: Any) -> dict[str, Any]:
    return {
        "id": f"R-{number:04d}",
        "claim_id": f"C-{claim:04d}",
        "claim": f"Invented claim {claim}.",
        "claim_type": "empirical",
        "contestable": True,
        "anchor": {"exact": f"invented anchor {claim}"},
        "key": "exampleStudy2026",
        "no_identifier_reason": "Invented source for this test",
        "locator": {"page": number},
        "quote": QUOTE,
        "quote_hash": N1_HASH,
        "relation": "supports",
        "justification": "The quoted sentence states both counts.",
        "retrieved_via": "pdf",
        "provenance": {**PROVENANCE, "date": "2026-03-04"},
        **extra,
    }


RECORDS = [record(1, 1), record(2, 1), record(5, 2)]
HEADER = {"schema_version": "0.3.0", "work": WORK, "created": "2026-03-01"}

YAML_TEXT = """\
ledger:
  schema_version: 0.3.0
  work:
    title: Example work
    type: manuscript
  created: 2026-03-01
records:
"""


def yaml_records() -> str:
    lines = []
    for r in RECORDS:
        lines.append(f"  - id: {r['id']}")
        lines.append(f"    claim_id: {r['claim_id']}")
        lines.append(f"    claim: {r['claim']}")
        lines.append("    claim_type: empirical")
        lines.append("    contestable: true")
        lines.append(f"    anchor: {{exact: {r['anchor']['exact']}}}")
        lines.append("    key: exampleStudy2026")
        lines.append("    no_identifier_reason: Invented source for this test")
        lines.append(f"    locator: {{page: {r['locator']['page']}}}")
        lines.append(f"    quote: {QUOTE}")
        lines.append(f"    quote_hash: {N1_HASH}")
        lines.append("    relation: supports")
        lines.append(f"    justification: {r['justification']}")
        lines.append("    retrieved_via: pdf")
        lines.append("    provenance:")
        lines.append("      by_type: agent")
        lines.append("      by: Claude Code")
        lines.append("      model: claude-opus-5-5")
        lines.append("      date: 2026-03-04")
    return "\n".join(lines) + "\n"


def write_json(path: Path, data: object) -> str:
    path.write_text(json.dumps(data), "utf-8")
    return str(path)


def test_yaml_with_unquoted_dates(tmp_path: Path) -> None:
    source = tmp_path / "old.yaml"
    source.write_text(YAML_TEXT + yaml_records(), "utf-8")
    target = str(tmp_path / "new.jsonl")

    result = import_ledger(str(source), target)

    assert result == {
        "path": target,
        "records": 3,
        "from_version": "0.3.0",
        "steps": ["0.3.0→0.4.0"],
        "problems": [],
    }
    header, records = ledger.read(target)
    assert header == {**HEADER, "schema_version": schema_version()}
    assert [r["id"] for r in records] == ["R-0001", "R-0002", "R-0005"]
    assert [r["claim_id"] for r in records] == ["C-0001", "C-0001", "C-0002"]
    assert all(r["provenance"]["date"] == "2026-03-04" for r in records)
    assert all(r["quote_hash"] == N1_HASH for r in records)


def test_json_object_shape(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": RECORDS})
    target = str(tmp_path / "new.jsonl")

    result = import_ledger(source, target)

    assert result["problems"] == []
    header, records = ledger.read(target)
    assert header["schema_version"] == schema_version()
    assert header["created"] == "2026-03-01"
    assert records == RECORDS


def test_header_without_created_gets_today(tmp_path: Path) -> None:
    header = {"schema_version": "0.3.0", "work": WORK}
    source = write_json(tmp_path / "old.json", {"ledger": header, "records": []})
    target = str(tmp_path / "new.jsonl")

    import_ledger(source, target)

    assert ledger.read(target)[0]["created"]


def test_plain_list_needs_work(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", RECORDS)
    target = str(tmp_path / "new.jsonl")

    with pytest.raises(ValueError, match="pass `work`"):
        import_ledger(source, target)
    assert not Path(target).exists()

    result = import_ledger(source, target, WORK)
    assert result["records"] == 3
    assert result["problems"] == []
    assert ledger.read(target)[0]["work"] == WORK


def test_header_and_work_conflict(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": RECORDS})
    target = str(tmp_path / "new.jsonl")

    with pytest.raises(ValueError, match="do not pass `work`"):
        import_ledger(source, target, WORK)
    assert not Path(target).exists()


def test_invalid_header_writes_nothing(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", {"ledger": {"work": {}}, "records": []})
    target = str(tmp_path / "new.jsonl")

    with pytest.raises(ValueError, match="Invalid header"):
        import_ledger(source, target)
    assert not Path(target).exists()


def test_existing_target_is_not_overwritten(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": RECORDS})
    target = tmp_path / "new.jsonl"
    target.write_text("keep\n", "utf-8")

    with pytest.raises(ValueError, match="already exists"):
        import_ledger(source, str(target))
    assert target.read_text("utf-8") == "keep\n"


def test_source_as_target_is_refused(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": RECORDS})

    with pytest.raises(ValueError, match="differ from source"):
        import_ledger(source, source)


def test_missing_ids_and_hashes_are_filled(tmp_path: Path) -> None:
    bare = [
        {k: v for k, v in r.items() if k not in ("id", "claim_id", "quote_hash")}
        for r in (record(1, 1), record(2, 2))
    ]
    bare.insert(0, record(7, 4))
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": bare})
    target = str(tmp_path / "new.jsonl")

    result = import_ledger(source, target)

    assert result["problems"] == []
    records = ledger.read(target)[1]
    assert [r["id"] for r in records] == ["R-0007", "R-0008", "R-0009"]
    assert [r["claim_id"] for r in records] == ["C-0004", "C-0005", "C-0006"]
    assert records[0]["quote_hash"] == N1_HASH
    assert records[1]["quote_hash"] == ledger.quote_hash(QUOTE)
    assert records[1]["quote_hash"].startswith("sha256-n2:")


def test_invalid_records_are_written_and_reported(tmp_path: Path) -> None:
    broken = {**record(1, 1), "relation": "invented"}
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": [broken]})
    target = str(tmp_path / "new.jsonl")

    result = import_ledger(source, target)

    assert result["records"] == 1
    assert any(p.startswith("R-0001:") for p in result["problems"])
    assert ledger.read(target)[1] == [broken]


def test_add_record_continues_numbering(tmp_path: Path) -> None:
    source = write_json(tmp_path / "old.json", {"ledger": HEADER, "records": RECORDS})
    target = str(tmp_path / "new.jsonl")
    import_ledger(source, target)

    added = ledger.add_record(
        target,
        {k: v for k, v in record(0, 0).items() if k not in ("id", "claim_id", "quote_hash")}
        | {"claim": "A new invented claim."},
        PROVENANCE,
    )

    assert added["id"] == "R-0006"
    assert added["claim_id"] == "C-0003"
    assert ledger.validate_ledger(target) == []


def write_jsonl(path: Path, lines: list[object]) -> str:
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", "utf-8")
    return str(path)


ALL_STEPS = ["0.2.0→0.3.0", "0.3.0→0.4.0"]


def test_jsonl_source_with_older_version(tmp_path: Path) -> None:
    header = {**HEADER, "schema_version": "0.2.0"}
    source = write_jsonl(tmp_path / "old.jsonl", [{"ledger": header}, *RECORDS])
    target = str(tmp_path / "new.jsonl")

    result = import_ledger(source, target)

    assert result["from_version"] == "0.2.0"
    assert result["steps"] == ALL_STEPS
    assert result["problems"] == []
    new_header, records = ledger.read(target)
    assert new_header["schema_version"] == schema_version()
    assert records == RECORDS


def test_jsonl_detected_by_header_line(tmp_path: Path) -> None:
    source = write_jsonl(tmp_path / "old.txt", [{"ledger": HEADER}, *RECORDS])
    result = import_ledger(source, str(tmp_path / "new.jsonl"))
    assert result["records"] == 3


def test_jsonl_bad_lines_are_named(tmp_path: Path) -> None:
    path = tmp_path / "old.jsonl"
    path.write_text(
        json.dumps({"ledger": HEADER}) + "\n{broken\n\n[1, 2]\n" + json.dumps(RECORDS[0]) + "\n",
        "utf-8",
    )
    target = tmp_path / "new.jsonl"

    with pytest.raises(ValueError, match="line 2 is not valid JSON; line 4 is not an object"):
        import_ledger(str(path), str(target))
    assert not target.exists()


def test_version_newer_than_server_is_refused(tmp_path: Path) -> None:
    header = {**HEADER, "schema_version": "99.0.0"}
    source = write_json(tmp_path / "new.json", {"ledger": header, "records": RECORDS})
    target = tmp_path / "out.jsonl"

    with pytest.raises(ValueError, match="newer than this server"):
        import_ledger(source, str(target))
    assert not target.exists()


def test_unknown_version_is_refused(tmp_path: Path) -> None:
    header = {**HEADER, "schema_version": "0.1.0"}
    source = write_json(tmp_path / "old.json", {"ledger": header, "records": RECORDS})

    with pytest.raises(ValueError, match=r"known versions: 0.2.0, 0.3.0, 0.4.0"):
        import_ledger(source, str(tmp_path / "out.jsonl"))


def test_current_version_needs_no_steps(tmp_path: Path) -> None:
    header = {**HEADER, "schema_version": schema_version()}
    source = write_json(tmp_path / "cur.json", {"ledger": header, "records": RECORDS})

    result = import_ledger(source, str(tmp_path / "out.jsonl"))

    assert result["steps"] == []


def test_pre_schema_list_runs_every_step(tmp_path: Path) -> None:
    source = write_json(tmp_path / "hand.json", RECORDS)

    result = import_ledger(source, str(tmp_path / "out.jsonl"), WORK)

    assert result["from_version"] is None
    assert result["steps"] == ALL_STEPS
