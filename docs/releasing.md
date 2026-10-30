# Releasing the MCP server and schema

Server releases are tagged `vX.Y.Z`; schema releases use `schema-vX.Y.Z` and do not trigger this workflow.

## MCP server

1. On a branch, set the version in `pyproject.toml`, run `uv lock`, and move the `[Unreleased]` entries in `CHANGELOG.md` under `## [X.Y.Z] - YYYY-MM-DD`. Merge the pull request.
2. Rehearse on TestPyPI: run the *Release* workflow manually on `main` (Actions → Release → Run workflow).
3. Tag the merged commit and push the tag: `git tag vX.Y.Z && git push origin vX.Y.Z`. The workflow checks that tag, package version, lockfile and changelog agree, runs CI, publishes to PyPI through trusted publishing, and creates the GitHub release.

Publishing needs the GitHub environments `pypi` and `testpypi`, and on PyPI and TestPyPI a trusted publisher for this repository with workflow `release.yml` and the matching environment.

If the GitHub release step fails after a draft was created, finish or delete that draft by hand; the workflow refuses to overwrite it.

## Schema

Schema tags do not publish a Python package or create a GitHub release automatically.

1. Confirm that the schema identifier and title, README, private ledger headers and development repository copy agree on the schema version. Update `schema/CHANGELOG.md` with the release notes. Validate the schema and run the required repository checks.
2. Merge the release preparation through a pull request. After the user approves the schema release, tag the merged commit with `schema-vX.Y.Z` and push that tag.
3. Create a GitHub release for the schema tag using its entry in `schema/CHANGELOG.md`. Attach only the public schema and its licence notice if standalone assets are wanted; never attach private ledgers or their exports.

## Coordinated first release

The prepared pair is server `v0.1.0` and schema `schema-v0.4.0`. They may tag the same merged commit, while retaining independent versioning and release notes. Publish the schema release and rehearse the server on TestPyPI before publishing the server tag. The server wheel includes the schema and its separate CC BY 4.0 licence notice.
