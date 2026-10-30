"""Inspect release archives and smoke-test the wheel outside the source checkout."""

from __future__ import annotations

import argparse
import os
import subprocess
import tarfile
import tempfile
import tomllib
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "evidence_ledger_mcp"
WHEEL_FILES = ("__init__.py", "server.py", "schema.py", "evidence-ledger.schema.json")


def check_members(names: list[str], *, sdist: bool) -> None:
    paths = [Path(name) for name in names]
    if sdist:
        paths = [Path(*path.parts[1:]) for path in paths]
    for path in paths:
        if "ledger" in path.parts[:1] or path.suffix in {".yaml", ".jsonl"}:
            raise ValueError(f"Possible private ledger in distribution: {path}")
        if any(part in {".git", ".venv", "__pycache__"} for part in path.parts):
            raise ValueError(f"Local content in distribution: {path}")
    if not sdist:
        for name in WHEEL_FILES:
            if Path(PACKAGE, name) not in paths:
                raise ValueError(f"Missing packaged file: {name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    sdists = list(args.dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Expected exactly one wheel and one sdist")
    wheel = wheels[0].resolve()
    with zipfile.ZipFile(wheel) as archive:
        check_members(archive.namelist(), sdist=False)
    with tarfile.open(sdists[0]) as tar:
        check_members(tar.getnames(), sdist=True)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = pyproject["project"]["version"]
    with tempfile.TemporaryDirectory(prefix="evidence-ledger-wheel-check-") as tmp:
        work = Path(tmp)
        environment = work / "venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        scripts = environment / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}

        def run(*arguments: str) -> None:
            subprocess.run([str(python), *arguments], cwd=work, env=env, check=True)

        run("-m", "pip", "install", "-q", str(wheel))
        run("-m", "pip", "check")
        run(
            "-c",
            "import importlib.metadata as m; import evidence_ledger_mcp.schema as s; "
            f"assert m.version('evidence-ledger-mcp') == {version!r}; "
            f"assert not s.__file__.startswith({str(ROOT)!r}); "
            "print('Installed wheel supports schema', s.schema_version())",
        )
    print(f"Distribution checks passed for {version}")


if __name__ == "__main__":
    main()
