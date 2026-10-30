"""Validate a release ref against the package metadata and extract its dated changelog entry."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_notes(root: Path, ref: str, event: str) -> str:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version: str = project["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Only stable X.Y.Z releases are supported")
    if event == "push":
        if ref != f"refs/tags/v{version}":
            raise ValueError("Release tag must match package version")
    elif event == "workflow_dispatch":
        if ref != "refs/heads/main":
            raise ValueError("TestPyPI rehearsals must run from main")
    else:
        raise ValueError(f"Unsupported release event: {event}")
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    locked = next(package for package in lock["package"] if package["name"] == project["name"])
    if locked["version"] != version:
        raise ValueError("Lockfile version must match package version")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\n(.*?)(?=^## \[|\Z)",
        changelog,
    )
    if not match or not match[1].strip():
        raise ValueError("Missing dated release notes")
    return match[1].strip() + "\n\nPublished by the repository's GitHub Actions release workflow.\n"


if __name__ == "__main__":
    notes = release_notes(ROOT, os.environ["RELEASE_REF"], os.environ["RELEASE_EVENT"])
    (ROOT / "release-notes.md").write_text(notes, encoding="utf-8")
