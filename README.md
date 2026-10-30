# evidence-ledger-mcp

> **Under active development.** Both the schema and the server may change in breaking ways between versions until v1.0. Pin the version you use.

An [MCP](https://modelcontextprotocol.io) server through which agents keep an evidence ledger for the citations in a work: for each claim, the source that backs it, where in the source, a short quote and why the citation is needed. Co-authors, scripts or a second model can then check every citation against its source.

**Server: [v0.1.0 on PyPI](https://pypi.org/project/evidence-ledger-mcp/0.1.0/) · [server release](https://github.com/matthiaskloft/evidence-ledger-mcp/releases/tag/v0.1.0).**

**Supported schema: [v0.4.0](https://github.com/matthiaskloft/evidence-ledger-schema/releases/tag/schema-v0.4.0) · [standalone schema repository](https://github.com/matthiaskloft/evidence-ledger-schema).**

The schema and server have independent versions, repositories and releases. This server vendors an exact schema revision in `schema/`; [schema/UPSTREAM.json](schema/UPSTREAM.json) records the upstream commit and file hashes. Builds and runtime validation do not fetch the schema. Original `schema-v*` releases here remain historical records; future schema releases belong in the schema repository.

The MCP server and its associated documentation use the [MIT licence](LICENSE). The bundled schema uses [CC BY 4.0](schema/LICENSE), with attribution to Matthias Kloft. These licences do not cover ledger contents or third-party source material.

## What it does

- **Write ledgers safely.** Records are validated against the schema before they are appended. The server assigns record and claim IDs, computes quote hashes and dates the provenance instead of leaving them to the agent.
- **Keep the history.** The server never deletes records; a withdrawn record keeps its reason.
- **Find gaps.** Search by claim, source key or text, and list contestable claims still missing evidence.
- **Share without leaking sources.** Exports and summaries come at three levels: `full` (private), `masked` (short excerpts) and `locator` (no quoted text). A publication check refuses to write a file that carries more source text than its level allows.
- **Read it as a report.** A standalone HTML summary, grouped by claim, prints to PDF from a browser.
- **See the evidence in the work.** The claims are marked in the work's own HTML and linked to their evidence, as end notes or in a side panel.
- **Check it against the work and its sources.** Find anchors that no longer appear in the work, records assessed against another revision, quotes that the source text no longer holds, and citation keys missing from the bibliography.

## Ledger format

Ledgers follow the [evidence ledger schema](https://github.com/matthiaskloft/evidence-ledger-schema#readme), which documents the purpose, the file shapes, record fields, quote hashing, a minimal example and the sources the fields draw on. The server bundles a pinned copy in [`schema/`](schema/).

The server stores ledgers as JSON Lines (`.jsonl`, one record per line), because new records are appended as single lines, concurrent additions rarely conflict, and agents write JSON reliably. It reads JSON Lines and exports JSON or JSON Lines; YAML ledgers written by hand remain valid under the schema.

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
4. `export_ledger` or `summarize_ledger` at `masked` or `locator` level to share the ledger with co-authors, reviewers or a journal.

### Exports and summaries

`export_ledger` defaults to `level="full"`, `format="jsonl"` and excluding withdrawn records. Keep full exports private. Use `level="masked"` with optional `max_words` (1–25) for excerpts, or `level="locator"` to remove quoted source text. Exports retain other record metadata, including `note` and header `notes`, and always remove `locator.chunk`. A publication check rejects copied source text in other metadata at masked and locator levels; it does not replace publication approval. The output must be a new file.

Masked exports accept `max_words` from 1 to 25. With a focus they keep a centred window, shifting at the quote edges to use the budget; otherwise they keep the start and end. Cuts are marked with “…”; quotes shorter than the budget stay whole. A focus longer than the budget is refused. Without `max_words`, masking still keeps only the first and last words (at most three each and half the quote), even with a focus. The export header records `level` and `max_words`.

`summarize_ledger` writes a self-contained HTML report grouped by claim, with `full`, `masked` and `locator` levels. Print it from a browser to produce a PDF; the server does not write PDFs directly. Masked summaries use the default start/end masking and do not accept `max_words`.

`embed_ledger(path, work, out, level, layout, include_withdrawn)` takes the HTML of the work (rendered by Quarto, Pandoc or any tool) and writes a copy to a new file in which each claim's `anchor.exact` text is marked and followed by its claim ID, linked to an evidence card. Layout `endnotes` collects the cards in an "Evidence" section before `</body>`. Layout `panel` keeps that section and, with JavaScript, also opens a clicked mark's card in a fixed side panel (a sidebar from 1100 px width, where the first claim's card is open at load; a bottom sheet on narrower screens). Enter opens a mark, the left and right arrow keys step through the claims and, on narrow screens, Esc closes the sheet. Without JavaScript the page shows the end section only. If no anchor is located, `panel` falls back to `endnotes` and the result's `layout` says `endnotes`. Anchor text is matched after normalising curly quotes, dashes and ellipses, and a match on word boundaries is preferred. Anchors that have only a marker, are not found, or overlap text already marked for another claim go into a "Not located in the work" list (an overlapping one notes "overlaps C-xxxx") and are returned in `not_located`; `overlapping` maps each such claim ID to the claim it overlaps. When a located claim has records whose anchors differ, the card lists the others. A record's key links to `#ref-<key>` when the work has that element (as Pandoc and Quarto emit); otherwise the DOI or URL link remains. Levels and the publication check work as for `summarize_ledger`; unlocated anchors show no work text at the `masked` and `locator` levels. The work's text is not changed apart from the marks, claim-ID superscripts and an end section, but the output sets its own page-wide light/dark theme (following the system setting) and adds a hint line for `panel`; the added styles use `el-` class names. `out` must be in the same folder as the work, so relative links to figures, styles and scripts still resolve. The output is UTF-8: a charset the work declares is changed to `utf-8`. A `full` result holds whole quotes: keep it private.

`check_ledger(path, work, revision, bibliography, sources, include_withdrawn, source_urls)` reads the ledger and writes nothing. Its result holds record IDs, claim IDs, keys and counts, never quote or source text, so it can be shown or logged anywhere. `records` counts the records checked and `claims` their distinct claim IDs; withdrawn records count only with `include_withdrawn`. `gaps` is always returned: `missing_evidence` maps each contestable record to the fields among `locator`, `quote` and `justification` that it lacks, and `claims_without_records` lists claims whose records are all withdrawn (whatever `include_withdrawn` says). The other checks run when their input is given. `work` is a path (HTML, Markdown, Quarto, LaTeX or plain text); `anchors` counts the anchors checked and lists records whose `anchor.exact` text is not found (`not_found`; HTML is matched as in `embed_ledger`, on the visible text. Other files are matched against their source text, after collapsing whitespace and typography, so markup inside an anchor, such as emphasis, a link, `\emph{}` or `[@key]`, reports `not_found`; check anchors against the rendered HTML where you can) and those with only a marker (`marker_only`). `revision` lists records whose `provenance.manuscript_rev` differs (`different`) or is missing (`unknown`). `bibliography` is a `.bib` or CSL JSON file; record keys missing from it are listed under `gaps.keys_missing_from_bibliography`. Without one, the `ref-<key>` entries of an HTML work serve, if it has any. `sources` maps a record `key` to the source's full text, which the agent supplies; each quote is compared after n2 normalisation and listed as `matched`, `not_found` or `no_source`. `matched` means the quote's letters and digits appear in order in the source, since n2 ignores spacing, punctuation and word boundaries. Records without a quote are left out of `quotes`. `source_urls` maps a record `key` to a public `http` or `https` URL whose text the server fetches itself and adds to `sources` (a key in both is an error). HTML is reduced to its visible text; plain text is used as is; other types, such as PDF, fail. The server refuses hosts that resolve to non-public addresses (loopback, private, link-local), on every redirect too (at most 5), allows 15 seconds per fetch in total (redirects included; the DNS lookup is not timed) and reads at most 10 MB. A fetch that fails does not raise an error: `quotes.fetch_failed` maps its key to a short reason (such as `non-public address`, `too large`, `HTTP 404` or `timeout`), and the records of that key count as `no_source`. Fetched text is not returned or stored. Withdrawn records are skipped unless `include_withdrawn` is set.
