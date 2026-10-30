# Releasing the MCP server

Server releases are tagged `vX.Y.Z`; schema releases use `schema-vX.Y.Z` and do not trigger this workflow.

## MCP server

1. On a branch, set the version in `pyproject.toml`, run `uv lock`, and move the `[Unreleased]` entries in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`. Merge the pull request.
2. Rehearse on TestPyPI: run the *Release* workflow manually on `main` (Actions → Release → Run workflow).
3. Tag the merged commit and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`. The workflow checks that tag, package version, lockfile and changelog agree, runs CI, publishes to PyPI through trusted publishing, and creates the GitHub release.

Publishing needs the GitHub environments `pypi` and `testpypi`, and on PyPI and TestPyPI a trusted publisher for this repository with workflow `release.yml` and the matching environment.

If the GitHub release step fails after a draft was created, finish or delete that draft by hand; the workflow refuses to overwrite it.

## Schema updates

The canonical schema is released independently in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema). Do not create new schema releases in this server repository. Original `schema-v*` tags and release pages remain historical records and never trigger server publishing.

To adopt an upstream schema release, follow [schema/README.md](../schema/README.md), update its pinned revision and hashes, and run the server checks and distribution checks. The server wheel bundles the schema and its CC BY 4.0 licence notice. A server release should state which schema version it supports.

The first server release was `v0.1.0`, supporting schema `schema-v0.4.0`. Future releases need not be synchronized.
