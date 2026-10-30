# Roadmap

Plans for the evidence ledger MCP server. They describe intentions, not commitments, and may change; there are no dates. Schema changes are planned and released separately in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema).

The server works on its own: it does not depend on other MCP servers or on a particular reference manager. For the planned source checks, agents will pass in source text, or the server will fetch a public URL itself.

## 0.1: core ledger (implemented)

- Create a ledger with a header (`schema_version`, `work`).
- Add records: the server computes `quote_hash`, assigns IDs, fills in `provenance` and validates each record before appending it to the JSON Lines file.
- Read, find and list records, e.g. by claim, by source key, or records still missing evidence.
- Validate a whole ledger.
- Withdraw records (`withdrawn`) instead of deleting them.

## 0.2: export levels (implemented)

Every export is produced at one of the levels `full`, `masked` or `locator`, and runs the publication check before anything is written, so that no export carries more source text than its level allows.

- **Levels:** `full` keeps every field; `masked` keeps the first and last words of each quote by default, or up to `max_words` (1–25), centred on `quote_focus` when supplied; `locator` keeps key, locator, hash and other metadata, but no quoted source text. Masked and locator exports remove quote context and `quote_focus`. Every level drops local lookup hints (`locator.chunk`).
- **Publication check:** refuse to write an export that contains source text beyond its level.
- **Machine-readable export:** the ledger as JSON or JSON Lines at the chosen level, for reviewers, journals and other tools.

## 0.3: ledger summary (implemented)

- A standalone report of all records, grouped by claim, as HTML that prints to PDF from a browser (the server writes no PDF).
- Annotations readable without hovering and in print.

## 0.4: embedded rendering

Status: the HTML part is implemented (`embed_ledger`); PDF/LaTeX output is still planned.

- The work itself, with each backed claim linked to its evidence. Standard formats are HTML (interactive) and PDF. The server supplies the claim data and the filters or packages a document toolchain needs (Pandoc/Quarto, LaTeX); it does not bundle that toolchain.
- Links from each record's `key` to the work's bibliography.

## 0.5: checks

- Check that each anchor still appears in the work, and flag records assessed against an earlier revision of it.
- Re-check quotes against source text passed in by the agent or fetched from a public URL.
- A gap report: contestable claims without locator, quote or justification, claims without records, and citation keys missing from the bibliography.

### Link resolution

A ledger carries only portable identifiers (DOI, ISBN, URL, title), the locator and `quote_hash`; nothing specific to one computer. Whoever opens a ledger, its author or a recipient, can resolve the links against their own library:

- Match each source in a local Zotero library or a folder of PDFs, by DOI, ISBN, URL and title.
- Find the passage in the reader's copy by its `quote_hash`; normalization n2 tolerates whitespace, punctuation and case differences, with legacy n1 hashes still checkable. A changed wording can still change the hash.
- Write the result to a local link file that stays on the reader's computer and is never shared.
- Report per record: passage found, source found but passage not found, or source not in the library. A found passage confirms the record independently.

A recipient can then rebuild the links in an export without the author's files.

## 0.6: library links in exports

- Links from each record to the source in the reader's own library (a Zotero item or a local PDF, opened at the page of the passage), read from the local link file (see 0.5). Without it, exports link to the DOI or URL.

## Testing throughout

- A small example work that cites only public sources (web pages, open-access articles, documentation) serves as the test fixture for every feature.
- Tests that fetch these sources run in a separate CI job, so that an unavailable website does not block other changes; the default tests run offline.

## Under consideration

- An HTML editor: click a record, edit its fields in a side panel, save it back into the ledger, with the edit recorded as a human one.
- A review log of who checked which record, and when.
- Several agents writing to the same ledger at the same time.
- Reconsider whether the free-text `note` and `notes` fields should appear in public exports; currently they are retained and checked for copied source text.

Ideas and requests are welcome as [issues](https://github.com/matthiaskloft/evidence-ledger-mcp/issues).
