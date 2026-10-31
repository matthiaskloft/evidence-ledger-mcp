# Agent instructions

These instructions apply to every coding agent working in this repository (Claude Code, Codex and others). `CLAUDE.md` is a symlink to this file.

## Schema ownership

This repository owns the MCP server. The canonical evidence ledger schema is maintained separately in `matthiaskloft/evidence-ledger-schema`.

- `schema/` contains a pinned vendored release, not the schema's development source. Do not edit its schema, licence or changelog directly. Update all three from an upstream release and record its exact revision, version, tag and file hashes in `schema/UPSTREAM.json`.
- Update supported-schema documentation, including the schema badge at the top of the README, and run all checks when adopting a new schema release. Keep one schema copy in this repository; the wheel receives its copy at build time.
- Propose schema changes in the schema repository. Original `schema-v*` tags here are historical; future schema releases belong upstream.

## Pull requests

- Resolve every review conversation on a pull request once it is addressed (fixed, or answered with why not); auto-merge waits until all conversations are resolved.

## MCP server code

- Python ≥ 3.11, managed with uv; source in `src/evidence_ledger_mcp/`, tests in `tests/`.
- Before every commit: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` (strict) and `uv run pytest`. Do not silence a check with `# noqa` or `# type: ignore` without a comment saying why.
- `schema/evidence-ledger.schema.json` is the only copy of the schema in the repository; the wheel gets its copy at build time. Never duplicate it under `src/`.
- Server releases are tagged `vX.Y.Z` (see `docs/releasing.md`); never create or push a release tag without the user's approval. Skip the TestPyPI rehearsal unless `release.yml`, the packaging or the PyPI setup changed: the tag run validates and tests before it publishes.

## Ledgers for our own citations

Every citation we add to this repository (README, docs, code comments, schema descriptions) gets a record in our own evidence ledger, following `schema/evidence-ledger.schema.json`.

- Keep **separate ledgers** for the two contributions:
  - `ledger/schema.yaml` for citations in the schema, its documentation and the README sections about it.
  - `ledger/server.yaml` for citations in the MCP server code and its documentation.
- The ledgers are YAML for now and move to JSON Lines (`ledger/schema.jsonl`, `ledger/server.jsonl`) once the MCP server writes them; convert them then, in one step.
- The ledgers are **private**. `ledger/` is git-ignored because records hold verbatim quotes from copyrighted sources. Never commit a ledger, force-add it, or copy quotes from it into tracked files.
- Add or update the record in the same change that adds or edits the citation, and check that its `anchor.exact` text still appears in the file.
- Recompute `quote_hash` whenever a quote changes, and validate the ledger against the schema before committing.
- Start each ledger with a header (`schema_version`, `work`). Use `note` and `notes` for comments, never for source text: they are exported with the ledger.
- Enable the pre-commit hook once per clone with `git config core.hooksPath .githooks`, and install PyYAML for the `python` it runs (`python -m pip install pyyaml`). It runs `tools/check_public.py --staged`, which blocks commits that contain ledger files, quote fields, quotes from the private ledgers, or email addresses other than noreply addresses. CI runs the same check on all tracked files. Never bypass it with `--no-verify`.
- Take quotes only from the source itself (full text or PDF). Never write a quote from memory; if no passage can be found, say so instead of creating a record.

## Publishing ledgers later

We may later publish exported versions of the ledgers, at the `masked` level (first and last words of each quote, plus locator and hash) or the `locator` level (key, locator and hash only). A `masked` export still contains source text, so it may be published only after the legal review allows it and a person has approved the release. Agents never decide on their own to publish a ledger or any export of one.
