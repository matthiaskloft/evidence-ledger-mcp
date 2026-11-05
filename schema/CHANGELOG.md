# Schema changelog

Schema releases are independent of MCP server releases and use `schema-vX.Y.Z` tags.

## [0.5.1] - 2026-11-05

- Add example-value tables for every record and header field, including nested fields.
- Clarify optional and conditional fields in the README and field reference, including required children of optional objects and omission versus empty values.
- Update the schema identifier and title for this patch release; validation rules are unchanged from v0.5.0.

## [0.5.0] - 2026-11-05

- Replace reserved `evidence_kind` with optional `evidence_type`: `reference` (default), `analysis_output`, or `source_code`. Choose by the supporting evidence's role, regardless of file format.
- Add report-first analysis artifacts with optional generating scripts, and code artifacts with exactly one local path or HTTPS URL, exact byte hashes, and locators. Reuse quote fields for result and code excerpts.
- Allow an optional `analysis.script.locator` for a function, notebook cell, or line range in the generating script.
- Define analysis dependencies in `derived_from` as unique record IDs, with cross-record existence and cycle checks.
- Require bibliographic identifiers and top-level locators only for references; preserve common contestability and quote rules for all types.
- Move the new schema identifier to this repository's versioned raw GitHub namespace. Document migration, artifact verification, exports, and downstream compatibility.

## [0.4.0] - 2026-10-30

- Define n2 quote hashing: Unicode NFKC, casefold, NFKC again, then retain letters and digits. Legacy n1 hashes remain checkable.
- Add optional `quote_focus`, requiring a `quote`. The focus identifies a unique phrase of at most 25 whole whitespace-delimited words. The server checks these semantic constraints in addition to JSON Schema validation.
- Add export header fields `level` and `max_words`. An integer word budget is limited to 1–25 and requires the masked level; null preserves default masking.
- License the schema under CC BY 4.0; see `LICENSE`.

The MCP server v0.1.0 supports this schema. This release does not change the schema version beyond the v0.4.0 already recorded in its identifier and title.
