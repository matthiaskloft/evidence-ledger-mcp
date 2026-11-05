# Schema versions and storage

The schema and server have independent versions, repositories and releases. This server vendors an exact schema revision in [`schema/`](../schema/); [schema/UPSTREAM.json](../schema/UPSTREAM.json) records the upstream commit and file hashes. Builds and runtime validation do not fetch the schema. Original `schema-v*` releases here remain historical records; future schema releases belong in the schema repository.

To adopt a new schema release, follow [schema/README.md](../schema/README.md).

## Storage format

The server stores ledgers as JSON Lines (`.jsonl`, one record per line), because new records are appended as single lines, concurrent additions rarely conflict, and agents write JSON reliably. It reads JSON Lines and exports JSON or JSON Lines; YAML ledgers written by hand remain valid under the schema.

## Supported evidence

The bundled schema is v0.5.1. `evidence_type` is optional and defaults to `reference`; references keep bibliographic identifiers and a top-level `locator`. `analysis_output` uses `analysis.report` and optionally `analysis.script`; `source_code` uses `source_code`. Primary artifacts require exactly one local `path` or HTTPS `url`, an exact-byte `sha256`, and a textual `locator`. Script hashes and locators are optional. Local artifact paths are relative to the ledger file. Contestable records of every type still require `quote`, `quote_hash` and `justification`.

`validate_record` checks record structure and quote focus. `validate_ledger` additionally checks that analysis `derived_from` IDs exist, IDs are unique throughout the dependency context, and dependencies are acyclic, including records in `related` ledgers. Additions and updates enforce these dependencies too; moves refuse to leave dependencies unreachable from either ledger and its supplied related ledgers. Supply all related ledgers when dependencies cross files. Completeness checks use each evidence type's artifact field instead of a reference locator; bibliography checks apply only to references. HTML summaries show artifact metadata. The PDF-specific `resolve_links` and `relink_html` tools skip analysis-output and source-code records. Moves, imports and exports rebase relative artifact paths to keep identifying the same files; absolute paths and URLs stay unchanged. Exports retain artifact metadata and dependencies and apply the same quote masking and leak checks to all types. An export that would omit a withdrawn dependency is refused before writing; use `include_withdrawn=True` to retain it.

Artifact hashes identify exact file bytes, independently of normalized quote hashes. Validation does not read, download or execute artifacts: verify their hashes, locate their excerpts in the actual files, and assess their support separately. Do not put code or results into artifact locators; excerpts belong in the quote fields.

Use `import_ledger` to upgrade older ledgers into a new file. Reserved literature evidence is mapped to reference evidence. Legacy analysis evidence requires manual report metadata and exact file hashes; invalid records are retained and reported for correction. Existing v0.5.0 ledgers remain valid without header changes because they have the same validation rules as v0.5.1; importing updates the header without changing them.
