# Changelog

Changes to the MCP server package `evidence-ledger-mcp`. Schema changes are released separately under `schema-vX.Y.Z` tags. Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Package scaffold: a stub server with the tools `schema_info` and `validate_record`, linting (ruff), type checking (mypy, strict), tests, and CI and release workflows.
- Core ledger tools (roadmap 0.1): `create_ledger`, `add_record`, `get_record`, `find_records`, `validate_ledger` and `withdraw_record`, storing ledgers as JSON Lines. The server assigns record and claim IDs, computes `quote_hash` and fills in the provenance date.
- Export (roadmap 0.2): `export_ledger` writes the ledger as JSON or JSON Lines at the level `full`, `masked` or `locator`. Every level drops `locator.chunk`. A publication check runs before writing and refuses an export in which any field other than the claim and anchor shares a run of 24 letters or digits with a quote, prefix or suffix; an existing file is never overwritten.
