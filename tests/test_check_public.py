import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_public", Path(__file__).resolve().parents[1] / "tools" / "check_public.py"
)
assert spec is not None and spec.loader is not None
check_public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_public)


def test_private_focus_is_matched_in_staged_markdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    private = tmp_path / "ledger"
    private.mkdir()
    focus = "Invented focus phrase with enough letters"
    (private / "schema.yaml").write_text(
        f"- id: R-0001\n  quote: Before {focus} after\n  quote_focus: {focus}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(check_public, "files", lambda staged: ["notes.md"])
    monkeypatch.setattr(check_public, "content", lambda path, staged: focus)
    monkeypatch.setattr(check_public.sys, "argv", ["check_public.py", "--staged"])
    assert check_public.main() == 1
    assert "quote_focus" in capsys.readouterr().err
