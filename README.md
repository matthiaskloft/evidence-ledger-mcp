# evidence-ledger-mcp

> **Under active development.** Both the schema and the server may change in breaking ways between versions until v1.0. Pin the version you use.

This repository holds two separate contributions:

1. **The evidence ledger schema** (`schema/`): a format for structured records that make every citation in a work (a manuscript, software or other) checkable. It stands on its own: any tool or agent can write and check ledgers with it, without our server. Status: draft v0.4.0, may still change in breaking ways.
2. **The evidence ledger MCP server** (`src/`, Python package `evidence-ledger-mcp`): a tool through which agents write and check ledgers that follow the schema. Status: early; it creates, appends to, searches, validates and withdraws records in JSON Lines ledgers (roadmap 0.1) and exports them at the levels full, masked or locator (roadmap 0.2), and writes an HTML summary grouped by claim that prints to PDF (roadmap 0.3), and embeds the claims in the HTML of the work itself (roadmap 0.4, HTML part). Checks are planned.

The two have separate version numbers. Schema releases are tagged `schema-vX.Y.Z`; the server currently supports schema v0.4.0 and reports it through `schema_info`. The schema will move to a repository of its own before v1.0.

The evidence ledger schema in `schema/` is licensed under Creative Commons Attribution 4.0 International (CC BY 4.0); see [schema/LICENSE](schema/LICENSE). Attribution: Matthias Kloft. This licence applies to the schema, not to ledger contents or third-party source material. The MCP server and its associated documentation are licensed under the MIT licence; see [LICENSE](LICENSE). The schema retains its separate CC BY 4.0 licence, including the copy bundled with the server.

## Purpose

When an LLM agent or a person adds a citation, the ledger records what is claimed, which source backs it, where in the source, a short quote, and why the citation is needed. Co-authors, scripts or a second model can then check each citation against its source later, whichever tool wrote the work. The idea follows Moravcsik's *active citation* (2014): contestable claims come with the evidence that supports them.

## The schema

[`schema/evidence-ledger.schema.json`](schema/evidence-ledger.schema.json) (JSON Schema 2020-12) describes one record and, in `$defs/header`, the ledger header. A ledger is a list of records, kept next to the work it covers.

**Header.** A ledger can start with a header that records `schema_version`, the `work` it covers (`title`, `type`: `manuscript`, `software`, `dataset` or `other`, and an optional `location`), and optional `description`, `created` and `notes`. The ledger file then takes one of these shapes:

- JSON or YAML: an object `{"ledger": <header>, "records": [<record>, ...]}`.
- JSON Lines: the first line is `{"ledger": <header>}`; every following line is one record.
- A plain list of records, without header, stays valid.

**File format.** The schema is format-neutral: it validates parsed records, so a ledger can be JSON, JSON Lines or YAML. The MCP server stores ledgers as JSON Lines (`.jsonl`, one record per line), because new records are appended as single lines, concurrent additions rarely conflict, and agents write JSON reliably. The schema also supports records written by hand in YAML; the server reads JSON Lines and exports JSON or JSON Lines. When writing YAML, quote dates (`date: "2026-10-30"`), since unquoted dates are not read as text.

Each record contains:

- **Claim:** `claim`, `claim_id` (records backing the same claim share it), `claim_type`, and an `anchor` that finds the claim in the work (an ID marker, or the exact text).
- **Source:** a citation `key`, and a `doi`, `isbn` or `url` (or `no_identifier_reason`).
- **Evidence:** `locator` (page, section, figure or table), `quote`, `quote_hash`, `relation` (`supports`, `partially_supports`, `background`, `method`, `contrasts`), a `justification` and an optional `note`.
- **Provenance:** who wrote the record (person or agent, and which model) and when.

Every claim counts as `contestable` by default and then needs locator, quote, hash and justification. Marking a claim as not contestable needs a `contestable_reason`. Evidence that contradicts a claim is recorded with `relation: contrasts`, not dropped.

`note` (per record) and `notes` (in the header) are free-text comments, the JSON counterpart of comments in a YAML file. They are exported with the ledger, so they must never contain source text; source text belongs only in `quote`, `quote_prefix`, `quote_suffix` and `quote_focus`.

`quote_hash` is `sha256-n2:` plus the SHA-256 of the UTF-8 quote after normalization n2: Unicode NFKC, casefold, NFKC again, keep only letters and digits. Legacy `sha256-n1:` hashes omit the second NFKC and remain valid and checkable. The hash then survives differences between copies of a source, such as whitespace, hyphenation and quote styles.

`quote_focus` optionally marks the phrase within `quote` that carries the claim. It must occur exactly once, cover whole whitespace-delimited words, and contain at most 25 words. It is source text and is removed from masked and locator exports.

Masked exports accept `max_words` from 1 to 25. With a focus they keep a centred window, shifting at the quote edges to use the budget; otherwise they keep the start and end. Cuts are marked with “…”; quotes shorter than the budget stay whole. A focus longer than the budget is refused. Without `max_words`, masking still keeps only the first and last words (at most three each and half the quote), even with a focus. The export header records `level` and `max_words`.

## How to use it

1. When you cite a source, write one record per claim–source pair into the ledger.
2. Validate the ledger against the schema with any JSON Schema 2020-12 validator, e.g. in Python with `jsonschema`.

A minimal record:

```yaml
- id: R-0001
  claim_id: C-0001
  claim: "Keeping a ledger cut unchecked citations from 40 to 3 per manuscript."
  claim_type: empirical
  contestable: true
  anchor: {exact: "cut unchecked citations from 40 to 3"}
  key: exampleLedgerStudy2026
  no_identifier_reason: "Invented source for this example"
  locator: {page: 4}
  quote: "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
  quote_hash: sha256-n2:3b8d67a25018dccc865ee88b24c10aa4a5b553e41ff28ebc46936a71eee7db3c
  relation: supports
  justification: "The quoted sentence states both counts."
  retrieved_via: pdf
  provenance: {by_type: agent, by: Claude Code, model: claude-opus-5-5, date: "2026-10-30"}
```

Quotes from copyrighted sources belong in a private ledger. A public ledger should keep only locators and hashes.

## Running the MCP server

Requires Python 3.11 or newer. From a source checkout with uv installed:

```bash
uv sync
uv run evidence-ledger-mcp
```

The server uses stdio. Configure an MCP client to run `uv` with arguments `run`, `--directory`, the absolute path to this checkout, and `evidence-ledger-mcp`. Pass absolute ledger paths to tools; relative paths resolve against the server's working directory.

Available tools are `schema_info`, `validate_record`, `create_ledger`, `add_record`, `get_record`, `find_records`, `validate_ledger`, `withdraw_record`, `export_ledger`, `summarize_ledger` and `embed_ledger`. Create a ledger with a `work` containing `title` and `type`, then pass records and a separate `provenance` object to `add_record`. The server assigns record IDs, assigns claim IDs unless supplied, computes n2 quote hashes and fills in the provenance date.

`export_ledger` defaults to `level="full"`, `format="jsonl"` and excluding withdrawn records. Keep full exports private. Use `level="masked"` with optional `max_words` (1–25) for excerpts, or `level="locator"` to remove quoted source text. Exports retain other record metadata, including `note` and header `notes`, and always remove `locator.chunk`. A publication check rejects copied source text in other metadata at masked and locator levels; it does not replace publication approval. The output must be a new file.

`summarize_ledger` writes a self-contained HTML report grouped by claim, with `full`, `masked` and `locator` levels. Print it from a browser to produce a PDF; the server does not write PDFs directly. Masked summaries use the default start/end masking and do not accept `max_words`.

`embed_ledger(path, work, out, level, layout, include_withdrawn)` takes the HTML of the work (rendered by Quarto, Pandoc or any tool) and writes a copy to a new file in which each claim's `anchor.exact` text is marked and followed by its claim ID, linked to an evidence card. Layout `endnotes` collects the cards in an "Evidence" section before `</body>`. Layout `panel` keeps that section and, with JavaScript, also opens a clicked mark's card in a fixed side panel (a sidebar from 1100 px width, where the first claim's card is open at load; a bottom sheet on narrower screens). Enter opens a mark, the left and right arrow keys step through the claims and, on narrow screens, Esc closes the sheet. Without JavaScript the page shows the end section only. If no anchor is located, `panel` falls back to `endnotes` and the result's `layout` says `endnotes`. Anchor text is matched after normalising curly quotes, dashes and ellipses, and a match on word boundaries is preferred. Anchors that have only a marker, are not found, or overlap text already marked for another claim go into a "Not located in the work" list (an overlapping one notes "overlaps C-xxxx") and are returned in `not_located`; `overlapping` maps each such claim ID to the claim it overlaps. When a located claim has records whose anchors differ, the card lists the others. A record's key links to `#ref-<key>` when the work has that element (as Pandoc and Quarto emit); otherwise the DOI or URL link remains. Levels and the publication check work as for `summarize_ledger`; unlocated anchors show no work text at the `masked` and `locator` levels. The work's text is not changed apart from the marks, claim-ID superscripts and an end section, but the output sets its own page-wide light/dark theme (following the system setting) and adds a hint line for `panel`; the added styles use `el-` class names. The output is UTF-8: a charset the work declares is changed to `utf-8`. A `full` result holds whole quotes: keep it private.

## Where the fields come from

| Field or rule | Basis |
| --- | --- |
| `contestable` (full evidence for contestable claims) | Active citation: only citations that support contestable empirical points need full documentation, not background references or uncontested facts (Moravcsik, 2014, pp. 50–51) |
| `anchor.exact`, `anchor.prefix`, `anchor.suffix`, `quote_prefix`, `quote_suffix` | W3C Web Annotation Text Quote Selector: a passage is identified by an exact copy plus the text before and after it (Sanderson et al., 2017, §4.2.4) |
| `relation` | Loosely follows CiTO, the Citation Typing Ontology (Peroni & Shotton, 2012); the mapping onto CiTO terms is not yet checked. `supports` and `contrasts` also match scite's citation classes (Nicholson et al., 2021) |
| Claim, passage and justification in one record | Annotation for Transparent Inquiry links passages in a publication to annotations and underlying sources (Karcher & Weber, 2019) |
| `provenance` | Records who asserted what and when, in the spirit of nanopublications (Groth et al., 2010); a record could be exported in that form |
| `claim_id`, `importance`, `retrieved_via`, `found_via`, `quote_hash`, `no_identifier_reason`, `withdrawn` | Our own proposals; to the best of our knowledge they do not follow an earlier source |

### References

- Groth, P., Gibson, A., & Velterop, J. (2010). The anatomy of a nanopublication. *Information Services & Use, 30*(1–2), 51–56. https://doi.org/10.3233/ISU-2010-0613
- Karcher, S., & Weber, N. (2019). Annotation for transparent inquiry: Transparent data and analysis for qualitative research. *IASSIST Quarterly, 43*(2), 1–9. https://doi.org/10.29173/iq959
- Moravcsik, A. (2014). Transparency: The revolution in qualitative research. *PS: Political Science & Politics, 47*(1), 48–53. https://doi.org/10.1017/S1049096513001789
- Nicholson, J. M., Mordaunt, M., Lopez, P., Uppala, A., Rosati, D., Rodrigues, N. P., Grabitz, P., & Rife, S. C. (2021). scite: A smart citation index that displays the context of citations and classifies their intent using deep learning. *Quantitative Science Studies, 2*(3), 882–898. https://doi.org/10.1162/qss_a_00146
- Peroni, S., & Shotton, D. (2012). FaBiO and CiTO: Ontologies for describing bibliographic resources and citations. *Journal of Web Semantics, 17*, 33–43. https://doi.org/10.1016/j.websem.2012.08.001
- Sanderson, R., Ciccarese, P., & Young, B. (Eds.). (2017). *Web Annotation Data Model*. W3C Recommendation. https://www.w3.org/TR/2017/REC-annotation-model-20170223/
