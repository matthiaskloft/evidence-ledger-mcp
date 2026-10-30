# Contributing

Thank you for your interest in the evidence ledger schema and MCP server.

## Issues

Issues are welcome: questions, bug reports, suggestions for the schema, and pointers to related work we should know about. Please say which contribution an issue is about (the schema or the MCP server) and, for the schema, which version.

## Pull requests

Pull requests can only be opened by invited collaborators. If you would like to propose a change, please open an issue first; we will discuss it there.

## For collaborators

Enable the pre-commit hook once per clone:

```bash
git config core.hooksPath .githooks
python -m pip install pyyaml
```

The hook runs `python`, so install PyYAML for that interpreter.

It blocks commits that would publish private ledger content or personal email addresses. CI runs the same check on every pull request.
