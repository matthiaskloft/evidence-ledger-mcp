# Contributing

Thank you for your interest in the evidence ledger MCP server. Schema changes belong in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema); this repository vendors a pinned schema release.

## Issues

Issues are welcome: questions, bug reports, suggestions for the schema, and pointers to related work we should know about. Please say which contribution an issue is about (the schema or the MCP server) and, for the schema, which version.

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
