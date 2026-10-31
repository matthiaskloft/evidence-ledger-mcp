# Changelog

Changes to the MCP server package `evidence-ledger-mcp`. Schema changes are released separately in [evidence-ledger-schema](https://github.com/matthiaskloft/evidence-ledger-schema). Format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

## [0.4.0] - 2026-10-31

### Added

- `resolve_links` and `relink_html` take `link_map`, the path of a `.private.json` file that maps citation keys to PDFs (and optionally to a link that opens the item in the reader's library), as an alternative or addition to `folder` (#57). The map is validated against `link-map.schema.json`, shipped in the package. Keys missing from the map are reported `not_in_map` unless `folder` is also given. Cards in a relinked copy get an "Open in library" button, with the page appended.
- A folder file named `<citation key>.pdf` is now tried before DOI, ISBN and title matching (#57).
- Summaries and embedded endnotes open with a list of the claims, each linked to its card with a dot per record coloured by relation (#57).
- An embedded work can be switched between endnotes and the side panel with a button in its hint line; the reader's choice is remembered and `layout` only sets the view shown first (#57).
- Tool descriptions, server instructions and `docs/tools.md` recommend a `sources/` folder of only the cited PDFs, kept out of version control, warn against pointing `folder` at a whole library, and describe building the map with Zotero and Better BibTeX (#57).

### Changed

- Summary and embedded evidence cards share one calmer style: a 70-character reading width, two text sizes below the headings, the passage in the work styled like the quote with only its focal text underlined (also `quote_focus` in quotes), and the record details, including who added it, in one label/value list. The "Your copy" line of a relinked copy has small matching "Open PDF" and "Open in library" buttons that open in a new tab, with the file and page in their tooltip and a note only when the passage or PDF was not found (#57).

## [0.3.1] - 2026-10-31

### Fixed

- `resolve_links` marks a whole quote `across_pages` when it runs cleanly across a page break, not only when a running head, caption or sidebar sits between its two halves (#43). The `resolve_links` tool description says so too.
- The server instructions no longer repeat the fragment "server's working directory." after the source-text paragraph (#44).

## [0.3.0] - 2026-10-31

### Fixed

- `validate_ledger` reads the header `level`: it accepts the masked and locator exports `export_ledger` writes (a masked quote no longer fails the hash comparison, a locator record needs no `quote`) and reports source text a hand-edited export reintroduces (`quote`, `quote_prefix`, `quote_suffix` or `quote_focus` in a locator export, a masked quote over its word budget or another source field in a masked one). Validation cannot catch source text copied into `claim` or `justification`; the publication check at export time remains the guard.

### Added

- Server instructions tell agents to stop and tell the user when a tool fails or misleads, to suggest, never file, a bug report reproduced with an invented record, and to keep workflow failures in the ledger. A bug report issue template collects the details.
- `schema_info` also reports the server version.

### Changed

- Source text stays in the quote fields: the server instructions and the `add_record` description say that `justification`, `locator`, `note` and the header's `description` and `notes` are written in the agent's own words, and `add_record` now refuses a record whose fields outside the quote fields (and the work's `claim` and `anchor`) repeat 24 or more letters and digits of its own `quote`, `quote_prefix`, `quote_suffix` or `quote_focus`, naming the field; the header's `description` and `notes` are checked against the new record too, and `validate_ledger` reports the same overlaps, header included, for existing records. A section heading in `locator` that repeats the quote is refused as well, consistent with the export. The same rule already blocked masked and locator exports. The vendored schema carries no field descriptions for these; they belong upstream.

## [0.2.0] - 2026-10-31

### Fixed

- Fetching refuses IPv6 addresses that carry a non-public IPv4 address (6to4, local-use NAT64, IPv4-compatible and Teredo forms), as it already did for IPv4-mapped and well-known NAT64 ones.
- Link resolution: reading PDFs stops after 300 seconds per call, reported under `time_limit`, so a very large folder no longer blocks the server for hours; DOIs with a `doi:` or `http://dx.doi.org/` prefix are matched; `relink_html` names the copy of a file without a suffix `<name>.private.html` instead of a hidden `.private.html`; and neither tool replaces an existing file it did not write.
- PDF text extraction no longer hangs inside the running MCP server on Windows: the extraction process now gets its own standard streams instead of inheriting the server's stdin, which the server is blocked reading. This affected `check_ledger` with PDF `source_urls`.

### Added

- Link resolution is tested against three real open-access PDFs, fetched from their publishers and cached locally (never committed) by tests marked `network`, covering two-column layouts, ligatures, running heads, sidebars and captions at page breaks, printed page labels. Whole quotes split by a page break are now found (`across_pages`), and short bibliography titles match together with the first author's family name.
- Private relinked copies (roadmap 0.6): `relink_html` reads the records a summary or embedded HTML file carries and writes `<name>.private.html` next to it, whose evidence cards link to the reader's own PDFs, at the page where the passage was found or else at the cited `locator.page` (through the PDF's printed page labels when it has them). The copy is marked private in its name, title, a banner and a `noindex` tag; links are relative when the PDFs are inside the copy's folder, and absolute `file://` links otherwise. `summarize_ledger` and `embed_ledger` now add a non-executable JSON block with each record's `id`, `key`, identifiers, `locator`, `quote` (at the export's level) and `quote_hash`, and mark each card with `data-record`. `resolve_links` now requires a `.private.json` link file and records the cited page where no passage is found (`page_from`).
- Link resolution, PDF folders (roadmap 0.5): `resolve_links` matches each record's source to a PDF in a folder the reader names (by DOI, ISBN or bibliography title on its first pages, whatever the file is named; as last resorts, a file named after the `key`, or one named after the first author and year, such as `Smith 2020.pdf`), finds the quoted passage by `quote_hash`, from a whole quote or one masked to its first and last words (not a focus window from the middle of a quote, nor a masked quote across a page break), and writes a local link file with the file and page per record. Records are reported as `found`, `passage_not_found`, `source_not_found` or `not_searchable`; unreadable PDFs are listed with a short reason. No source text is returned.
- Embedded rendering, HTML part (roadmap 0.4): `embed_ledger` writes a copy of the work's HTML in which each claim's anchor text is marked and linked to an evidence card, as `endnotes` (an Evidence section at the end) or `panel` (the same end section plus, with JavaScript, a side panel that opens the clicked claim's card: a sidebar with the first claim open on wide screens, a bottom sheet on narrow ones; it falls back to `endnotes`, reported in `layout`, when no anchor is located). The output sets its own page-wide light/dark theme and adds a hint line, claim-ID superscripts and the end section. Anchors are matched after normalising typography and preferring word boundaries; unlocated anchors, including those overlapping another claim (`overlapping`), are listed without work text at the masked and locator levels; record keys link to `#ref-<key>` bibliography entries when the work has them. Levels and the publication check work as in `summarize_ledger`; an existing file is never overwritten.
- Checks (roadmap 0.5): `check_ledger` reads a ledger and reports, as record IDs, claim IDs, keys and counts only, the gaps (contestable records lacking locator, quote or justification, claims with all records withdrawn, record keys missing from the bibliography), anchors not found in the work or with only a marker (HTML, Markdown, Quarto, LaTeX or text), records assessed against another or an unknown manuscript revision, and quotes not found in source text passed in by the agent. The bibliography is a `.bib` or CSL JSON file, or the `ref-<key>` entries of an HTML work. Anchors in non-HTML works are matched against the source text, so markup inside an anchor reports not found; the rendered HTML is the better check. It writes nothing.
- Fetching sources (roadmap 0.5): `check_ledger` takes `source_urls`, mapping a record `key` to a public http(s) URL whose text (HTML or plain text, up to 10 MB) the server fetches itself and re-checks quotes against, alongside `sources`. Hosts resolving to non-public addresses are refused, including on every redirect (at most 5); failures are reported per key under `quotes.fetch_failed` with a short reason, and never end the check. Fetched text is neither returned nor stored. A key in both `sources` and `source_urls` is an error. The tests run offline; one test that fetches a real page is marked `network` and runs in its own non-blocking CI job.
- Fetching PDFs (roadmap 0.5): `source_urls` also accepts a URL that serves a PDF; its text layer is extracted with `pypdf` (new dependency, 6.21.4 or later) in a child process stopped after 15 seconds, up to 2000 pages and 20 million characters. `application/x-pdf` and octet-stream responses with a PDF header count as PDFs. PDFs needing a password, PDFs without text (scans), unreadable, too slow and too long ones are reported under `quotes.fetch_failed` (`encrypted pdf`, `no text in pdf`, `unreadable pdf`, `pdf too slow`, `pdf too long`). A word hyphenated across lines can make its quote `not_found`.

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
