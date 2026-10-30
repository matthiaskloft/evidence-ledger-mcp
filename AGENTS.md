# Agent instructions

These instructions apply to every coding agent working in this repository (Claude Code, Codex and others). `CLAUDE.md` is a symlink to this file.

## Two contributions

This repository holds two separate contributions (see README.md):

1. **The evidence ledger schema** in `schema/`, versioned and tagged `schema-vX.Y.Z`.
2. **The evidence ledger MCP server**, versioned on its own.

Keep changes to one contribution in their own commits and pull requests where possible. A breaking schema change needs a new schema version.

## Ledgers for our own citations

Every citation we add to this repository (README, docs, code comments, schema descriptions) gets a record in our own evidence ledger, following `schema/evidence-ledger.schema.json`.

- Keep **separate ledgers** for the two contributions:
  - `ledger/schema.yaml` for citations in the schema, its documentation and the README sections about it.
  - `ledger/server.yaml` for citations in the MCP server code and its documentation.
- The ledgers are **private**. `ledger/` is git-ignored because records hold verbatim quotes from copyrighted sources. Never commit a ledger, force-add it, or copy quotes from it into tracked files.
- Add or update the record in the same change that adds or edits the citation, and check that its `anchor.exact` text still appears in the file.
- Recompute `quote_hash` whenever a quote changes, and validate the ledger against the schema before committing.
- Enable the pre-commit hook once per clone with `git config core.hooksPath .githooks`. It runs `tools/check_public.py --staged`, which blocks commits that contain ledger files, quote fields, quotes from the private ledgers, or email addresses other than noreply addresses. CI runs the same check on all tracked files. Never bypass it with `--no-verify`.
- Take quotes only from the source itself (full text or PDF). Never write a quote from memory; if no passage can be found, say so instead of creating a record.

## Publishing ledgers later

We may later publish exported versions of the ledgers, at the `masked` level (first and last words of each quote, plus locator and hash) or the `locator` level (key, locator and hash only). A `masked` export still contains source text, so it may be published only after the legal review allows it and a person has approved the release. Agents never decide on their own to publish a ledger or any export of one.
