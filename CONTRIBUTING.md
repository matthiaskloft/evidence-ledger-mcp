# Contributing

Thank you for your interest in the evidence ledger MCP server. Schema changes belong in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema); this repository vendors a pinned schema release.

## Issues

Issues are welcome: questions, bug reports, feature requests and pointers to related work we should know about.

If you want a change to the schema, please also open an issue in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema/issues), stating the schema version, and link the two issues. The schema is changed there first; the server adopts it in a later release.

To report a server error or a misleading result, use the [bug report form](https://github.com/matthiaskloft/evidence-ledger-mcp/issues/new?template=bug_report.yml). Reproduce the problem with an invented record; leave out real quotes, claims, justifications, work titles, absolute paths, usernames and credentials. If an agent notices the problem, it suggests the form to you and helps you strip those details; it does not file the issue itself.

## Pull requests

Pull requests can only be opened by invited collaborators. If you would like to propose a change, please open an issue first; we will discuss it there.

## For collaborators

Set up the environment with [uv](https://docs.astral.sh/uv/) and enable the pre-commit hook once per clone:

```bash
uv sync --extra test
git config core.hooksPath .githooks
python -m pip install pyyaml
```

The hook runs `python`, so install PyYAML for that interpreter. It blocks commits that would publish private ledger content or personal email addresses, including a non-noreply commit address. CI runs the same content check on every pull request.

Before opening a pull request, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
```

Releases of the server are described in [docs/releasing.md](docs/releasing.md).
