from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from test_ledger import PROVENANCE, RECORD, WORK

from evidence_ledger_mcp import checks, export, ledger, links, migrate, summary
from evidence_ledger_mcp.schema import record_errors, schema_version


@pytest.fixture
def path(tmp_path: Path) -> str:
    result = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(result, WORK)
    return result


def artifact_record(kind: str = "analysis_output") -> dict[str, Any]:
    record = {k: v for k, v in RECORD.items() if k not in ("locator", "no_identifier_reason")}
    artifact = {"path": "report.txt", "sha256": "a" * 64, "locator": "Result 1"}
    record["evidence_type"] = kind
    record["analysis" if kind == "analysis_output" else "source_code"] = (
        {"report": artifact} if kind == "analysis_output" else artifact
    )
    return record


@pytest.mark.parametrize("kind", ["analysis_output", "source_code"])
def test_artifact_lifecycle(path: str, tmp_path: Path, kind: str) -> None:
    added = ledger.add_record(path, artifact_record(kind), PROVENANCE)
    assert ledger.validate_ledger(path) == []
    assert ledger.find_records(path, missing_evidence=True) == []
    bib = tmp_path / "empty.json"
    bib.write_text("[]", encoding="utf-8")
    gaps = checks.check_ledger(path, bibliography=str(bib))["gaps"]
    assert gaps["missing_evidence"] == {}
    assert gaps["keys_missing_from_bibliography"] == {}
    html = summary._record(added)
    assert kind in html and "report.txt" in html and "a" * 64 in html
    for level in ("masked", "locator"):
        target = str(tmp_path / f"{level}.jsonl")
        export.export_ledger(path, target, level=level)
        assert ledger.validate_ledger(target) == []
        result = ledger.read(target)[1][0]
        assert result.get("analysis", result.get("source_code")) == added.get(
            "analysis", added.get("source_code")
        )
        assert result["quote_hash"] == added["quote_hash"]
        assert result.get("quote") != added["quote"]


def test_artifact_rules(path: str) -> None:
    added = ledger.add_record(path, artifact_record(), PROVENANCE)
    for invalid in (
        {**added, "locator": {"page": 1}},
        {**added, "analysis": {}},
        {
            **added,
            "analysis": {
                "report": {
                    "path": "x",
                    "url": "https://example.org/x",
                    "sha256": "a" * 64,
                    "locator": "Result",
                }
            },
        },
        {**added, "analysis": {"report": {"path": "x", "sha256": "bad", "locator": "Result"}}},
    ):
        assert record_errors(invalid)


def test_dependencies_and_atomic_cycle_refusal(path: str) -> None:
    first = ledger.add_record(path, artifact_record(), PROVENANCE)
    second = ledger.add_record(
        path, {**artifact_record(), "derived_from": [first["id"]]}, PROVENANCE
    )
    before = Path(path).read_bytes()
    with pytest.raises(ValueError, match="cycle"):
        ledger.update_record(path, first["id"], {"derived_from": [second["id"]]})
    assert Path(path).read_bytes() == before
    with pytest.raises(ValueError, match="missing record"):
        ledger.add_record(path, {**artifact_record(), "derived_from": ["R-9999"]}, PROVENANCE)
    assert Path(path).read_bytes() == before
    rows = ledger.read(path)[1]
    rows[0]["derived_from"] = [second["id"]]
    Path(path).write_text(
        "\n".join(json.dumps(x) for x in [{"ledger": ledger.read(path)[0]}, *rows]) + "\n",
        encoding="utf-8",
    )
    assert any("cycle" in error for error in ledger.validate_ledger(path))


def test_related_dependencies(path: str, tmp_path: Path) -> None:
    other = str(tmp_path / "other.jsonl")
    ledger.create_ledger(other, WORK)
    first = ledger.add_record(other, artifact_record("source_code"), PROVENANCE)
    ledger.add_record(
        path, {**artifact_record(), "derived_from": [first["id"]]}, PROVENANCE, related=[other]
    )
    assert any("missing record" in error for error in ledger.validate_ledger(path))
    assert ledger.validate_ledger(path, related=[other]) == []


@pytest.mark.parametrize("version", ["0.4.0", "0.5.0"])
def test_import_recent_versions(tmp_path: Path, version: str) -> None:
    record = {
        **RECORD,
        "id": "R-0001",
        "claim_id": "C-0001",
        "quote_hash": ledger.quote_hash(RECORD["quote"]),
        "provenance": {**PROVENANCE, "date": "2026-11-05"},
    }
    if version == "0.4.0":
        record["evidence_kind"] = "literature"
    source = tmp_path / "old.json"
    source.write_text(
        json.dumps({"ledger": {"schema_version": version, "work": WORK}, "records": [record]}),
        encoding="utf-8",
    )
    target = str(tmp_path / "new.jsonl")
    result = migrate.import_ledger(str(source), target)
    assert result["problems"] == []
    header, records = ledger.read(target)
    assert header["schema_version"] == schema_version()
    assert records[0]["quote_hash"] == record["quote_hash"]
    assert "evidence_kind" not in records[0]


def test_patch_version_remains_valid(path: str) -> None:
    header, _ = ledger.read(path)
    header["schema_version"] = "0.5.0"
    Path(path).write_text(json.dumps({"ledger": header}) + "\n", encoding="utf-8")
    assert ledger.validate_ledger(path) == []


@pytest.mark.parametrize("kind", ["analysis_output", "source_code"])
def test_artifact_metadata_cannot_repeat_excerpt(path: str, kind: str) -> None:
    record = artifact_record(kind)
    artifact = record["analysis"]["report"] if kind == "analysis_output" else record["source_code"]
    artifact["locator"] = record["quote"]
    before = Path(path).read_bytes()
    with pytest.raises(ValueError, match="Source text outside"):
        ledger.add_record(path, record, PROVENANCE)
    assert Path(path).read_bytes() == before


def test_invalid_dependencies_are_reported_on_import(tmp_path: Path) -> None:
    record = {
        **artifact_record(),
        "id": "R-0001",
        "claim_id": "C-0001",
        "derived_from": ["R-9999"],
        "provenance": {**PROVENANCE, "date": "2026-11-05"},
    }
    source = tmp_path / "old.json"
    source.write_text(
        json.dumps({"ledger": {"schema_version": "0.5.0", "work": WORK}, "records": [record]}),
        encoding="utf-8",
    )
    result = migrate.import_ledger(str(source), str(tmp_path / "new.jsonl"))
    assert any("missing record R-9999" in p for p in result["problems"])


def test_pdf_links_skip_artifacts(path: str) -> None:
    reference = ledger.add_record(path, RECORD, PROVENANCE)
    analysis = ledger.add_record(path, artifact_record(), PROVENANCE)
    assert links._rows([reference, analysis], include_withdrawn=False) == [
        (reference["id"], reference)
    ]
    assert "evidence_type" in summary.RELINK_FIELDS


def test_move_preserves_dependency_reachability(path: str, tmp_path: Path) -> None:
    first = ledger.add_record(path, artifact_record("source_code"), PROVENANCE)
    ledger.add_record(path, {**artifact_record(), "derived_from": [first["id"]]}, PROVENANCE)
    target = str(tmp_path / "target.jsonl")
    ledger.create_ledger(target, WORK)
    before = Path(path).read_bytes(), Path(target).read_bytes()
    with pytest.raises(ValueError, match="Invalid dependencies after move"):
        ledger.move_record(path, first["id"], target)
    assert (Path(path).read_bytes(), Path(target).read_bytes()) == before
    ledger.move_record(path, first["id"], target, related=[path, target])
    assert ledger.validate_ledger(path, related=[target]) == []
    assert ledger.validate_ledger(target, related=[path]) == []


@pytest.mark.parametrize("operation", ["move", "import", "export"])
@pytest.mark.parametrize("kind", ["analysis_output", "source_code"])
def test_relocation_preserves_artifact_targets(tmp_path: Path, operation: str, kind: str) -> None:
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    source = str(source_dir / "ledger.jsonl")
    target = str(target_dir / "ledger.jsonl")
    ledger.create_ledger(source, WORK)
    record = artifact_record(kind)
    if kind == "analysis_output":
        record["analysis"]["script"] = {"path": "scripts/run.py"}
    added = ledger.add_record(source, record, PROVENANCE)
    original_bytes = Path(source).read_bytes()
    if operation == "move":
        ledger.create_ledger(target, WORK)
        ledger.move_record(source, added["id"], target)
    elif operation == "import":
        assert migrate.import_ledger(source, target)["problems"] == []
    else:
        export.export_ledger(source, target, level="locator")
    relocated = ledger.read(target)[1][0]
    artifact = (
        relocated["analysis"]["report"] if kind == "analysis_output" else relocated["source_code"]
    )
    assert (target_dir / artifact["path"]).resolve() == (source_dir / "report.txt").resolve()
    assert artifact["sha256"] == "a" * 64
    if kind == "analysis_output":
        assert (target_dir / relocated["analysis"]["script"]["path"]).resolve() == (
            source_dir / "scripts/run.py"
        ).resolve()
    assert ledger.validate_ledger(target) == []
    if operation != "move":
        assert Path(source).read_bytes() == original_bytes


@pytest.mark.parametrize("level", ["full", "masked", "locator"])
def test_export_refuses_to_omit_withdrawn_dependency(path: str, tmp_path: Path, level: str) -> None:
    first = ledger.add_record(path, artifact_record("source_code"), PROVENANCE)
    ledger.add_record(path, {**artifact_record(), "derived_from": [first["id"]]}, PROVENANCE)
    ledger.withdraw_record(path, first["id"], "Superseded implementation")
    target = str(tmp_path / "export.jsonl")
    with pytest.raises(ValueError, match="include_withdrawn=True"):
        export.export_ledger(path, target, level=level)
    assert not Path(target).exists()
    export.export_ledger(path, target, level=level, include_withdrawn=True)
    assert ledger.validate_ledger(target) == []


def test_duplicate_related_ids_cannot_hide_cycle(path: str, tmp_path: Path) -> None:
    first = ledger.add_record(path, artifact_record(), PROVENANCE)
    a_header, _ = ledger.read(path)
    a_record = {**first, "id": "R-0003", "claim_id": "C-0003", "derived_from": ["R-0001"]}
    b_record = {**first, "id": "R-0001", "claim_id": "C-0001", "derived_from": ["R-0003"]}
    c_record = {**first, "id": "R-0001", "claim_id": "C-0002"}
    related = []
    for name, row in (("a.jsonl", a_record), ("b.jsonl", b_record), ("c.jsonl", c_record)):
        file = tmp_path / name
        file.write_text(
            json.dumps({"ledger": a_header}) + "\n" + json.dumps(row) + "\n", encoding="utf-8"
        )
        related.append(str(file))
    problems = ledger.validate_ledger(related[0], related=related[1:])
    assert any("duplicate id in dependency context" in p for p in problems)
    assert any("cycle" in p for p in problems)
    before = Path(related[0]).read_bytes()
    with pytest.raises(ValueError, match="duplicate id in dependency context"):
        ledger.add_record(related[0], artifact_record(), PROVENANCE, related=related[1:])
    assert Path(related[0]).read_bytes() == before


@pytest.mark.parametrize("artifact_path", ["", "https://example.org/report.txt"])
def test_relocation_keeps_invalid_paths_invalid(tmp_path: Path, artifact_path: str) -> None:
    record = artifact_record()
    record["analysis"]["report"]["path"] = artifact_path
    assert (
        ledger.relocate_artifacts(
            record, str(tmp_path / "a/ledger.jsonl"), str(tmp_path / "b/ledger.jsonl")
        )
        == record
    )


def test_relocation_keeps_absolute_paths_and_urls(tmp_path: Path) -> None:
    record = artifact_record()
    record["analysis"]["report"]["path"] = str((tmp_path / "report.txt").resolve())
    record["analysis"]["script"] = {"url": "https://example.org/run.py"}
    assert (
        ledger.relocate_artifacts(
            record, str(tmp_path / "a/ledger.jsonl"), str(tmp_path / "b/ledger.jsonl")
        )
        == record
    )


def test_repeated_related_paths_do_not_duplicate_records(path: str, tmp_path: Path) -> None:
    other = str(tmp_path / "other.jsonl")
    alias = str(tmp_path) + "/./other.jsonl"
    ledger.create_ledger(other, WORK)
    first = ledger.add_record(other, artifact_record("source_code"), PROVENANCE)
    related = [other, alias, other]
    second = ledger.add_record(
        path, {**artifact_record(), "derived_from": [first["id"]]}, PROVENANCE, related=related
    )
    assert second["id"] == "R-0002"
    assert ledger.validate_ledger(path, related=related) == []
    ledger.update_record(path, second["id"], {"note": "Review pending"}, related=related)
    assert ledger.validate_ledger(path, related=related) == []
