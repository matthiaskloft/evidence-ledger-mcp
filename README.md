# evidence-ledger-mcp

> **Under active development.** Both the schema and the server may change in breaking ways between versions until v1.0. Pin the version you use.

An MCP server through which agents create, append to, search, validate and withdraw records in JSON Lines evidence ledgers, export them at full, masked or locator levels, and generate printable HTML summaries. Source and anchor checks are planned.

**Server: [v0.1.0 on PyPI](https://pypi.org/project/evidence-ledger-mcp/0.1.0/) · [server release](https://github.com/matthiaskloft/evidence-ledger-mcp/releases/tag/v0.1.0).**

**Supported schema: [v0.4.0](https://github.com/matthiaskloft/evidence-ledger-schema/releases/tag/schema-v0.4.0) · [standalone schema repository](https://github.com/matthiaskloft/evidence-ledger-schema).**

The schema and server have independent versions, repositories and releases. This server vendors an exact schema revision in `schema/`; [schema/UPSTREAM.json](schema/UPSTREAM.json) records the upstream commit and file hashes. Builds and runtime validation do not fetch the schema. Original `schema-v*` releases here remain historical records; future schema releases belong in the schema repository.

The MCP server and its associated documentation use the [MIT licence](LICENSE). The bundled schema uses [CC BY 4.0](schema/LICENSE), with attribution to Matthias Kloft. These licences do not cover ledger contents or third-party source material.

## Ledger format

An evidence ledger records, for each citation, the claim, the source backing it, where in the source, a short quote and why the citation is needed. Ledgers follow the [evidence ledger schema](https://github.com/matthiaskloft/evidence-ledger-schema#readme), which documents the purpose, the file shapes, record fields, quote hashing, a minimal example and the sources the fields draw on. The server bundles a pinned copy in [`schema/`](schema/).

The server stores ledgers as JSON Lines (`.jsonl`, one record per line), because new records are appended as single lines, concurrent additions rarely conflict, and agents write JSON reliably. It reads JSON Lines and exports JSON or JSON Lines; YAML ledgers written by hand remain valid under the schema.

## Running the MCP server

Requires Python 3.11 or newer. From a source checkout with uv installed:

```bash
uv sync
uv run evidence-ledger-mcp
```

The server uses stdio. Configure an MCP client to run `uv` with arguments `run`, `--directory`, the absolute path to this checkout, and `evidence-ledger-mcp`. Pass absolute ledger paths to tools; relative paths resolve against the server's working directory.

Available tools are `schema_info`, `validate_record`, `create_ledger`, `add_record`, `get_record`, `find_records`, `validate_ledger`, `withdraw_record`, `export_ledger` and `summarize_ledger`. Create a ledger with a `work` containing `title` and `type`, then pass records and a separate `provenance` object to `add_record`. The server assigns record IDs, assigns claim IDs unless supplied, computes n2 quote hashes and fills in the provenance date.

`export_ledger` defaults to `level="full"`, `format="jsonl"` and excluding withdrawn records. Keep full exports private. Use `level="masked"` with optional `max_words` (1–25) for excerpts, or `level="locator"` to remove quoted source text. Exports retain other record metadata, including `note` and header `notes`, and always remove `locator.chunk`. A publication check rejects copied source text in other metadata at masked and locator levels; it does not replace publication approval. The output must be a new file.

Masked exports accept `max_words` from 1 to 25. With a focus they keep a centred window, shifting at the quote edges to use the budget; otherwise they keep the start and end. Cuts are marked with “…”; quotes shorter than the budget stay whole. A focus longer than the budget is refused. Without `max_words`, masking still keeps only the first and last words (at most three each and half the quote), even with a focus. The export header records `level` and `max_words`.

`summarize_ledger` writes a self-contained HTML report grouped by claim, with `full`, `masked` and `locator` levels. Print it from a browser to produce a PDF; the server does not write PDFs directly. Masked summaries use the default start/end masking and do not accept `max_words`.
