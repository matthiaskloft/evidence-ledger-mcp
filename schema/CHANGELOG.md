# Schema changelog

Schema releases are independent of MCP server releases and use `schema-vX.Y.Z` tags.

## [0.4.0] - 2026-10-30

- Define n2 quote hashing: Unicode NFKC, casefold, NFKC again, then retain letters and digits. Legacy n1 hashes remain checkable.
- Add optional `quote_focus`, requiring a `quote`. The focus identifies a unique phrase of at most 25 whole whitespace-delimited words. The server checks these semantic constraints in addition to JSON Schema validation.
- Add export header fields `level` and `max_words`. An integer word budget is limited to 1–25 and requires the masked level; null preserves default masking.
- License the schema under CC BY 4.0; see `LICENSE` in this directory.

The MCP server v0.1.0 supports this schema. This release does not change the schema version beyond the v0.4.0 already recorded in its identifier and title.
