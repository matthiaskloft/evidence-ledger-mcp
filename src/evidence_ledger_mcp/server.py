"""The MCP server: thin tool wrappers around the ledger functions."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.metadata import version
from typing import Any, Literal

from mcp.server.fastmcp import FastMCP

from evidence_ledger_mcp import checks, embed, export, ledger, links, summary
from evidence_ledger_mcp.schema import record_errors, schema_version

BUG_REPORT_URL = (
    "https://github.com/matthiaskloft/evidence-ledger-mcp/issues/new?template=bug_report.yml"
)

mcp = FastMCP(
    "evidence-ledger",
    instructions="Pass ledger paths as absolute paths; relative paths resolve against the "
    "server's working directory. Source text goes only into the quote fields (`quote`, "
    "`quote_prefix`, `quote_suffix`, `quote_focus`). Write every other field (`justification`, "
    "`locator`, `note`, and the header's `description` and `notes`) in your own words, because "
    "they are exported at every level; a run of 24 or more letters and digits from a quote there "
    "blocks masked and locator exports, and `add_record` and `update_record` refuse it. "
    "When a tool fails or a result looks wrong (a valid record "
    "rejected, an export that fails its own validation, a check that blocks an export without "
    "a clear reason), stop and tell the user; do not work around it or edit the ledger by hand "
    "to hide it. Suggest the user file " + BUG_REPORT_URL + "; never file it yourself, since "
    "posting publishes to a public repository. Reproduce the problem with an invented record, "
    "never real quotes, claims, justifications or work titles; leave out absolute paths, "
    "usernames and credentials. Include the server version from schema_info, the tool called, "
    "its arguments in shortened form and the exact error text. A source not found, a quote that "
    "cannot be located or a claim the source does not support is not a server bug: record it "
    "in the work and its ledger, not in an issue. "
    + "Finding the reader's PDFs (`resolve_links`, `relink_html`): put exactly the cited "
    "PDFs in one folder, e.g. `sources/` next to the ledger, named `<citation key>.pdf`, "
    "and pass it as `folder`; never point `folder` at a whole reference library "
    "(thousands of PDFs: slow, and it stops at the time limit with nothing found). Keep "
    "`sources/` out of version control (copyrighted PDFs). With a reference library, pass"
    " `link_map` instead: a file ending `.private.json` (schema `link-map.schema.json`, "
    "shipped in the package) mapping each citation key to its PDF `file` and optionally "
    "an `open` link into the library. For Zotero with Better BibTeX, call JSON-RPC "
    "`item.attachments(citekey)` at http://localhost:23119/better-bibtex/json-rpc, which "
    "returns `{open, path}` per attachment, and write those as `open` and `file`.",
)

# Mapping, not dict: FastMCP returns a dict result as is but wraps other types as {"result": ...},
# which keeps every ledger tool's result shape uniform.
Record = Mapping[str, Any]


@mcp.tool()
def schema_info() -> dict[str, str]:
    """Report the server version and the evidence ledger schema version it supports."""
    return {"server_version": version("evidence-ledger-mcp"), "schema_version": schema_version()}


@mcp.tool()
def validate_record(record: dict[str, Any]) -> list[str]:
    """Validate one ledger record against the schema; returns the violations, empty if valid."""
    return record_errors(record)


@mcp.tool()
def create_ledger(
    path: str, work: dict[str, Any], description: str | None = None, notes: str | None = None
) -> Record:
    """Create a ledger file (JSON Lines) with a header; `work` needs `title` and `type`."""
    return ledger.create_ledger(path, work, description, notes)


@mcp.tool()
def add_record(
    path: str,
    record: dict[str, Any],
    provenance: dict[str, Any],
    related: list[str] | None = None,
) -> Record:
    """Append a record. The server assigns `id`, `claim_id` (unless given), `quote_hash` and the
    provenance date, validates the result and returns the stored record. Mark the phrase
    carrying the claim (a number, term or short statement) with optional `quote_focus`. Source
    text belongs only in `quote`, `quote_prefix`, `quote_suffix` and `quote_focus`: write
    `justification`, `locator` (including a section heading) and `note` in your own words, since
    they are exported with masked and locator ledgers; a record that repeats 24 or more letters
    and digits of its own quote in another field is refused, naming the field. A project with
    several ledgers keeps ids unique across them: pass the other ledgers' paths as `related`
    every time, and the new `id` and `claim_id` are numbered past those of all of them."""
    return ledger.add_record(path, record, provenance, related)


@mcp.tool()
def update_record(
    path: str, id: str, changes: dict[str, Any], provenance: dict[str, Any]
) -> Record:
    """Change fields of one record and return it. `changes` is merged into the record; a null
    value removes a field. `id`, `withdrawn`, `quote_hash` and `provenance` cannot be changed,
    and a withdrawn record cannot be edited. A new `quote` gets a new `quote_hash`; a removed one
    drops it. The record's provenance becomes the given `provenance` with today's date. A
    change to `claim` or `importance` is copied to every record with the same `claim_id`,
    which keep their provenance. The same checks as `add_record` apply, and nothing is written
    when one fails."""
    return ledger.update_record(path, id, changes, provenance)


@mcp.tool()
def move_record(path: str, id: str, to: str) -> Record:
    """Move a record (withdrawn ones too) from the ledger at `path` to the ledger at `to`,
    keeping its `id`, `claim_id` and provenance, and return it. Refused when both are the same
    file, the id is missing from `path` or already used in `to`, or the record fails the checks
    of `add_record` against `to` (header text, claim text or importance of its claim). The
    record is written to `to` first, then removed from `path`; the id is not reused."""
    return ledger.move_record(path, id, to)


@mcp.tool()
def get_record(path: str, id: str) -> Record:
    """Return one record by its id."""
    return ledger.get_record(path, id)


@mcp.tool()
def find_records(
    path: str,
    claim_id: str | None = None,
    key: str | None = None,
    text: str | None = None,
    missing_evidence: bool = False,
    include_withdrawn: bool = False,
) -> list[dict[str, Any]]:
    """Find records by claim_id, source key, text in the claim, or contestable records lacking
    evidence (all filters combine); withdrawn records are left out unless requested."""
    return ledger.find_records(path, claim_id, key, text, missing_evidence, include_withdrawn)


@mcp.tool()
def validate_ledger(path: str, related: list[str] | None = None) -> list[str]:
    """Validate a whole ledger; returns the problems found, empty if valid. Pass the other
    ledgers of the project as `related` (the same list as for `add_record`) to also report ids
    used in more than one of them (`R-0001: id also used in <ledger>`)."""
    return ledger.validate_ledger(path, related)


@mcp.tool()
def withdraw_record(path: str, id: str, reason: str) -> Record:
    """Mark a record withdrawn with a reason instead of deleting it."""
    return ledger.withdraw_record(path, id, reason)


@mcp.tool()
def export_ledger(
    path: str,
    out: str,
    level: Literal["full", "masked", "locator"] = "full",
    format: Literal["json", "jsonl"] = "jsonl",
    include_withdrawn: bool = False,
    max_words: int | None = None,
) -> Record:
    """Export the ledger to a new file. `masked` keeps the first and last words of each quote,
    `locator` no quoted text; a publication check runs before writing, and `out` is never
    overwritten. `max_words` is allowed only for `masked`, from 1 to 25; None keeps the
    default masking. With a budget, `quote_focus` centres the excerpt. A `full` export
    holds whole quotes: keep it private."""
    return export.export_ledger(path, out, level, format, include_withdrawn, max_words)


@mcp.tool()
def summarize_ledger(
    path: str,
    out: str,
    level: Literal["full", "masked", "locator"] = "full",
    include_withdrawn: bool = False,
) -> Record:
    """Write a standalone HTML summary of the records, grouped by claim, to a new file. Levels
    and the publication check work as in `export_ledger`, and `out` is never overwritten. A
    `full` summary holds whole quotes: keep it private. For a PDF, print the HTML from a
    browser; its print style shows link targets and avoids splitting records where possible."""
    return summary.summarize_ledger(path, out, level, include_withdrawn)


@mcp.tool()
def embed_ledger(
    path: str,
    work: str,
    out: str,
    level: Literal["full", "masked", "locator"] = "full",
    layout: Literal["endnotes", "panel"] = "endnotes",
    include_withdrawn: bool = False,
) -> Record:
    """Write a copy of the work's HTML (`work`, rendered by Quarto, Pandoc or any tool) with each
    claim's anchor marked and linked to its evidence, to a new file. Both layouts end with an
    "Evidence" section holding one card per claim; a button switches the reader between that
    section and a side panel that opens the clicked claim's card (a bottom sheet on narrow
    screens), and `layout` picks the view shown first; if no anchor is located, `panel` falls
    back to `endnotes` and the result's `layout` says so.
    Anchors that are only a marker, not found in the text or overlapping another claim's marked
    text are listed under "Not located in the work" and returned in `not_located` (`overlapping`
    maps a claim to the one it overlaps); a record key links to `#ref-<key>` when the work has
    that bibliography entry. Levels and the publication check work as in `summarize_ledger`, and
    `out` is never overwritten and must be in the work's folder. A `full` result holds whole
    quotes: keep it private."""
    return embed.embed_ledger(path, work, out, level, layout, include_withdrawn)


@mcp.tool()
def check_ledger(
    path: str,
    work: str | None = None,
    revision: str | None = None,
    bibliography: str | None = None,
    sources: dict[str, str] | None = None,
    include_withdrawn: bool = False,
    source_urls: dict[str, str] | None = None,
) -> Record:
    """Check a ledger without changing anything; the result holds record and claim ids, keys and
    counts, never quote or source text. `gaps` is always returned: contestable records lacking a
    locator, quote or justification, claims whose records are all withdrawn, and, when a
    bibliography is known, record keys missing from it. Optional checks, each returned only when
    its input is given: `work` reports anchors not found in it, or with only a marker, under
    `anchors` (HTML is matched on its visible text; other files on their source text, so markup
    inside an anchor reports not found: prefer the rendered HTML); `revision` lists records assessed
    against another or an unknown `provenance.manuscript_rev`; `sources` maps a record `key` to the
    source's full text and re-checks each quote against it (`matched`, `not_found`, `no_source`);
    `source_urls` maps a record `key` to a public http(s) URL whose text (HTML, plain text or a
    PDF with a text layer, up to 10 MB; hyphenation across PDF lines can make a quote
    `not_found`) the server fetches itself and adds to `sources` (a key in both is an error).
    Hosts that are not public, including via redirects, are refused; fetches that fail are
    listed with a short reason under `quotes.fetch_failed`, and their records count as `no_source`.
    `bibliography` is a .bib or CSL JSON file; for an HTML `work` without one, its `ref-<key>`
    entries serve. Withdrawn records are skipped unless `include_withdrawn`."""
    return checks.check_ledger(
        path, work, revision, bibliography, sources, include_withdrawn, source_urls
    )


@mcp.tool()
def resolve_links(
    path: str,
    link_file: str,
    folder: str | None = None,
    bibliography: str | None = None,
    include_withdrawn: bool = False,
    link_map: str | None = None,
) -> Record:
    """Resolve the ledger's sources against the reader's own PDFs and write the result to
    `link_file`, which must end in `.private.json` (a rerun replaces one this tool wrote, no
    other file): it holds paths on this computer, so do not share it.
    Give `folder`, `link_map` or both. Best layout: a `sources/` folder holding only the cited
    PDFs, each named `<citation key>.pdf`, kept out of version control (copyrighted). A file
    named exactly after the key is tried first; other names work through the matching below.
    Do not pass a whole reference library as `folder`: thousands of PDFs are slow and the call
    stops at the time limit with every source `source_not_found`. For a library, pass
    `link_map` instead: the path of a `.private.json` file (JSON Schema `link-map.schema.json`)
    with `{"link_map_version": "0.1.0", "sources": {"<key>": {"file": "<pdf path>", "open":
    "<optional library link>"}}}`. A mapped key searches only its PDF; a key missing from the
    map is `not_in_map`, unless `folder` is also given, which is then searched for it. With
    Zotero and Better BibTeX, build the map from JSON-RPC `item.attachments(citekey)` at
    http://localhost:23119/better-bibtex/json-rpc, which returns `{open, path}` per attachment.
    `folder` is searched recursively.
    Where no passage is found, the link file still gives the PDF page of the record's
    `locator.page`, read through the PDF's printed page labels or, without labels, taken as the
    PDF page number (`page_from` says which). In a folder a source matches by the first
    of: a file named `<key>.pdf`, its DOI on a PDF's first two pages, its ISBN on the first ten,
    its title on the first two
    (from `bibliography`, a .bib or CSL JSON file, which can also supply DOI and ISBN; titles
    under 20 letters and digits count only with the first author's family name), each only if
    exactly one PDF matches, so that a PDF citing the source does not; last, a file named after
    the first author and year (e.g. `Ioannidis 2005.pdf`).
    Each record is then
    `found` (its passage is in the PDF, at the page given in the link file; this confirms the
    record independently), `passage_not_found`, `source_not_found`, `not_in_map` or
    `not_searchable`: finding a
    passage needs its quote, whole or masked to its first and last words as in `masked` exports;
    a `locator` export holds only the hash. The passage must hash to `quote_hash`, so
    whitespace, punctuation, case and line-end hyphens may differ; a whole quote split by a
    page break (with or without running heads or captions between its parts) is found and
    marked `across_pages` in the link file. PDFs that cannot be read are listed with a short
    reason under `unreadable_files`, and `time_limit` when reading PDFs stopped after 300 seconds.
    The result holds record ids and file paths, never source text."""
    return links.resolve_links(path, folder, link_file, bibliography, include_withdrawn, link_map)


@mcp.tool()
def relink_html(
    html: str,
    folder: str | None = None,
    bibliography: str | None = None,
    link_map: str | None = None,
) -> Record:
    """Give a reader links from a summary or embedded HTML file (from `summarize_ledger` or
    `embed_ledger`, e.g. one a co-author sent) to their own PDFs in `folder` (best: a `sources/`
    folder of only the cited PDFs named `<citation key>.pdf`, kept out of version control;
    never a whole library) or in a `link_map` (a `.private.json` file as for `resolve_links`).
    Records are read
    from the data the file carries, sources matched as in `resolve_links`, and each evidence card
    gets a "Your copy" line with an "Open PDF" button opening the PDF at the passage's page, or else
    at the cited page, and, where the map gives an `open` link, an "Open in library" button
    with the page appended (`?page=N`).
    Writes `<name>.private.html` next to the original (a rerun replaces a copy it wrote, no
    other file) and never changes
    the original. The copy is marked private in its name, title and a banner, and is not indexed:
    tell the user it links to files on this computer and must not be shared or published; they
    share the original instead. Links are relative when the PDFs are inside the copy's folder
    (so a team sharing that folder can open them), absolute file:// links otherwise; they work
    when the copy is opened from disk, not from a website. Returns record ids by status."""
    return links.relink_html(html, folder, bibliography, link_map)


def main() -> None:
    mcp.run()
