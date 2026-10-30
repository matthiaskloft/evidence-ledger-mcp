# Changelog

Changes to the MCP server package `evidence-ledger-mcp`. Schema changes are released separately under `schema-vX.Y.Z` tags. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Move canonical schema development and future schema releases to `evidence-ledger-schema`. Keep a pinned vendored schema for offline builds and validation, with its upstream revision and file hashes recorded in `schema/UPSTREAM.json`. Original schema tags remain historical records.

## [0.1.0] - 2026-10-30

### Added

- MCP server with the tools `schema_info` and `validate_record`, linting (ruff), type checking (mypy, strict), tests, and CI and release workflows.
- Core ledger tools (roadmap 0.1): `create_ledger`, `add_record`, `get_record`, `find_records`, `validate_ledger` and `withdraw_record`, storing ledgers as JSON Lines. The server assigns record and claim IDs, computes `quote_hash` and fills in the provenance date.
- Export (roadmap 0.2): `export_ledger` writes the ledger as JSON or JSON Lines at the level `full`, `masked` or `locator`. Every level drops `locator.chunk`. For masked and locator exports, a publication check runs before writing and rejects metadata sharing a run of 24 normalized letters or digits with a quote, prefix, suffix or focus, exempting the claim, anchor and permitted masked quote; an existing file is never overwritten.
- Optional `quote_focus` on records: validated as a unique phrase covering whole whitespace-delimited words, with at most 25 words.
- Optional `max_words` (1–25) for masked exports: keeps a window around `quote_focus`, or the start and end without a focus. Export headers record `level` and `max_words`; masked and locator exports remove `quote_focus`.
- Ledger summary (roadmap 0.3): `summarize_ledger` writes one self-contained HTML page of the records grouped by claim, at the level `full`, `masked` or `locator`, with the same publication check as `export_ledger`. All annotations are visible text, and a print stylesheet makes it printable to PDF from a browser; the server writes no PDF.
- MIT licence for the MCP server and its documentation; the bundled schema is separately licensed under CC BY 4.0.

### Changed

- New records use `sha256-n2` quote hashes (NFKC, casefold, NFKC again, letters and digits only). Validation still checks legacy `sha256-n1` hashes. The server now supports schema v0.4.0.
- The publication and repository privacy checks also inspect `quote_focus` for copied source text.
