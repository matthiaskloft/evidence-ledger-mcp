# Releasing the MCP server

Server releases are tagged `vX.Y.Z`; schema releases use `schema-vX.Y.Z` and do not trigger this workflow.

1. On a branch, set the version in `pyproject.toml`, run `uv lock`, and move the `[Unreleased]` entries in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`. Merge the pull request.
2. Rehearse on TestPyPI: run the *Release* workflow manually on `main` (Actions → Release → Run workflow).
3. Tag the merged commit and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`. The workflow checks that tag, package version, lockfile and changelog agree, runs CI, publishes to PyPI through trusted publishing, and creates the GitHub release.

Publishing needs the GitHub environments `pypi` and `testpypi`, and on PyPI and TestPyPI a trusted publisher for this repository with workflow `release.yml` and the matching environment.

If the GitHub release step fails after a draft was created, finish or delete that draft by hand; the workflow refuses to overwrite it.
