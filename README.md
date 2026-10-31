# evidence-ledger-mcp

> **Under active development.** Both the schema and the server may change in breaking ways between versions until v1.0. Pin the version you use.

An [MCP](https://modelcontextprotocol.io) server through which agents keep an evidence ledger for the citations in a work: for each claim, the source that backs it, where in the source, a short quote and why the citation is needed. Co-authors, scripts or a second model can then check every citation against its source.

It is built for academics: authors and co-authors who write with LLMs and want every citation to stay checkable. The ledger format is an open schema, so a graduate school could require it for theses, and a journal could adopt it for submissions or build its own standard on it.

**Server: [v0.1.0 on PyPI](https://pypi.org/project/evidence-ledger-mcp/0.1.0/) · [server release](https://github.com/matthiaskloft/evidence-ledger-mcp/releases/tag/v0.1.0).**

**Supported schema: [v0.4.0](https://github.com/matthiaskloft/evidence-ledger-schema/releases/tag/schema-v0.4.0) · [standalone schema repository](https://github.com/matthiaskloft/evidence-ledger-schema)** ([how schema versions are pinned](docs/schema.md)).

The MCP server and its associated documentation use the [MIT licence](LICENSE). The bundled schema uses [CC BY 4.0](schema/LICENSE), with attribution to Matthias Kloft. These licences do not cover ledger contents or third-party source material.

## The evidence ledger schema

Every ledger this server writes follows the **[evidence ledger schema](https://github.com/matthiaskloft/evidence-ledger-schema#readme)** (JSON Schema, draft 2020-12), currently **v0.4.0**. The schema is the contract: any tool, script or person can read, validate and check a ledger with it, with or without this server. Its README documents the purpose, the file shapes, every record field, quote hashing, a minimal example and the sources the fields draw on. The server bundles a pinned copy in [`schema/`](schema/) and reports the supported version through `schema_info`.

A ledger is a header (`schema_version`, `work` and optional notes) followed by records. Each record links one claim in the work to one source passage:

| Field | Required | Content |
| --- | --- | --- |
| `id`, `claim_id` | yes | Record and claim IDs; the server assigns them. Records about the same claim share a `claim_id`. |
| `claim`, `claim_type`, `contestable` | yes | The claim, its type (`empirical`, `definition`, `method`, `background`) and whether it needs full evidence; `false` needs a `contestable_reason`. |
| `anchor` | yes | Where the claim sits in the work: its `exact` text (with optional `prefix`/`suffix`) or a `marker`. |
| `key` | yes | The source's citation key, with `doi`, `isbn` or `url`, or a `no_identifier_reason`. |
| `locator` | | Where in the source: `page`, `section`, `figure` or `table`. |
| `quote`, `quote_focus` | | A short quote from the source, and the phrase within it that carries the claim; `quote_hash` is computed by the server. |
| `relation`, `justification` | `relation` | How the source bears on the claim (`supports`, `partially_supports`, `background`, `method`, `contrasts`) and why. |
| `retrieved_via`, `provenance` | yes | How the passage was found, and who assessed it (person or agent and model), when, and against which revision of the work. |
| `withdrawn` | | The reason a citation was withdrawn; records are never deleted. |

A minimal record, as passed to `add_record` (the server adds the IDs, hash and date):

```json
{
  "claim": "Retrieval practice improves long-term retention.",
  "claim_type": "empirical",
  "contestable": true,
  "anchor": {"exact": "testing improves later recall"},
  "key": "example2020",
  "doi": "10.1234/example",
  "locator": {"page": 12},
  "quote": "participants who were tested recalled more after one week",
  "relation": "supports",
  "justification": "Direct experimental evidence for the claim.",
  "retrieved_via": "pdf"
}
```

with `provenance` such as `{"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}`. Ledgers are stored as JSON Lines; see [docs/schema.md](docs/schema.md).

## What it does

- **Write ledgers safely.** Records are validated against the schema before they are appended. The server assigns record and claim IDs, computes quote hashes and dates the provenance instead of leaving them to the agent.
- **Keep the history.** The server never deletes records; a withdrawn record keeps its reason.
- **Find gaps.** Search by claim, source key or text, and list contestable claims still missing evidence.
- **Share without leaking sources.** Exports and summaries come at three levels: `full` (private), `masked` (short excerpts) and `locator` (no quoted text). A publication check refuses to write a file that carries more source text than its level allows.
- **Read it as a report.** A standalone HTML summary, grouped by claim, prints to PDF from a browser.
- **See the evidence in the work.** The claims are marked in the work's own HTML and linked to their evidence, as end notes or in a side panel.
- **Check it against the work and its sources.** Find anchors that no longer appear in the work, records assessed against another revision, quotes that the source text no longer holds, and citation keys missing from the bibliography. Source text can be passed in, or the server fetches it from public URLs (web pages, plain text and PDFs with a text layer).

## Installation

Requires Python 3.11 or newer. The server speaks MCP over stdio. With [uv](https://docs.astral.sh/uv/), run the released version from PyPI:

```bash
uvx --from evidence-ledger-mcp==0.1.0 evidence-ledger-mcp
```

For example, to add it to Claude Code:

```bash
claude mcp add evidence-ledger -- uvx --from evidence-ledger-mcp==0.1.0 evidence-ledger-mcp
```

Other MCP clients take the same command and arguments. To run a source checkout instead, use `uv sync`, then configure the client to run `uv` with arguments `run`, `--directory`, the absolute path to the checkout, and `evidence-ledger-mcp`.

Pass absolute ledger paths to tools; relative paths resolve against the server's working directory.

## Tools

| Tool | What it does |
| --- | --- |
| `schema_info` | Reports the supported schema version. |
| `create_ledger` | Creates a JSON Lines ledger with a header; `work` needs `title` and `type`. |
| `add_record` | Validates and appends a record; takes the record and a separate `provenance` object and returns the stored record. |
| `get_record` | Returns one record by its ID. |
| `find_records` | Finds records by `claim_id`, source `key` or claim `text`, or contestable records with `missing_evidence`. Filters combine; withdrawn records are left out unless `include_withdrawn` is set. |
| `validate_record` | Checks one record against the schema without writing it. |
| `validate_ledger` | Checks a whole ledger and lists the problems found. |
| `withdraw_record` | Marks a record withdrawn, with a reason, instead of deleting it. |
| `export_ledger` | Writes the ledger as JSON or JSON Lines at a chosen level to a new file. |
| `summarize_ledger` | Writes a standalone HTML summary grouped by claim to a new file. |
| `embed_ledger` | Marks each claim in the work's rendered HTML and links it to its evidence, as end notes or in a side panel, in a new file. |
| `check_ledger` | Reads the ledger and reports gaps, anchors missing from the work, records from another revision and quotes not found in source text you pass in or the server fetches from public URLs. Writes nothing. |

### Typical workflow

1. `create_ledger` once per work, next to the manuscript or code.
2. `add_record` whenever a source is cited, with the claim, its anchor, the source key, locator, quote, relation and justification. The server fills in IDs, the quote hash and the provenance date.
3. `find_records` with `missing_evidence` and `validate_ledger` before submission, to find claims still lacking evidence.
4. `check_ledger` with the rendered work, its bibliography and the sources (as text or public URLs), to catch anchors, keys and quotes that no longer match.
5. `export_ledger`, `summarize_ledger` or `embed_ledger` at `masked` or `locator` level to share the ledger with co-authors, reviewers or a journal.

The [tool reference](docs/tools.md) covers export levels, masking, embedding and every check in detail.
