"""Summarize a ledger as one self-contained HTML page, grouped by claim; prints to PDF."""

from __future__ import annotations

import json
from collections.abc import Callable
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from evidence_ledger_mcp import export, ledger
from evidence_ledger_mcp.ledger import Record

DATA_ID = "evidence-ledger-data"
RELINK_FIELDS = ("id", "key", "doi", "isbn", "url", "locator", "quote", "quote_hash")
LOCATOR_FIELDS = ("page", "section", "figure", "table")
QUOTES_SHOWN = {
    "full": "complete",
    "masked": "first and last words only",
    "locator": "none, locators only",
}
# One card per claim: the claim on top, its evidence below a rule, records split by
# rules. Metadata is small, muted and labelled in capitals so it never reads like claim or quote.
STYLE = """
:root {
  --bg: #f6f7f9; --card: #fff;
  --text: #1d2228; --muted: #5d6673;
  --line: #dde1e7; --accent: #2f5fb3;
  --supports: #2e7d4f; --partial: #9a6a00; --contrasts: #b23b3b; --other: #5d6673;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #15181d; --card: #1e2229;
    --text: #e4e7ec; --muted: #9aa3b0;
    --line: #343a44; --accent: #7aa2f7;
    --supports: #5cc489; --partial: #e0b040; --contrasts: #f07878; --other: #9aa3b0;
  }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text);
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 70ch; margin: 0 auto; padding: 2.5rem 1rem 5rem; }
a { color: var(--accent); text-decoration: underline; text-underline-offset: 0.15em; }
h1 { font-size: 1.5rem; line-height: 1.3; margin: 0 0 0.75rem; }
.id { font-weight: 600; font-size: 0.85rem; color: var(--muted); margin-right: 0.5rem; }
.meta { display: flex; flex-wrap: wrap; gap: 0.35rem 1.5rem; margin: 0.6rem 0;
  font-size: 0.85rem; color: var(--muted); }
.meta div { min-width: 6rem; }
.meta dt { font-size: 0.85rem; }
.meta dd { margin: 0; overflow-wrap: anywhere; color: var(--text); opacity: 0.8; }
section.claim { background: var(--card); border: 1px solid var(--line); border-radius: 10px;
  margin-top: 2.25rem; overflow: hidden; }
.claim-part { padding: 1.4rem 1.6rem 0.8rem; }
.evidence { border-top: 1px solid var(--line); padding: 0.4rem 1.6rem 1.2rem; }
.claim-text { font-size: 1.2rem; font-weight: 600; line-height: 1.45; margin: 0 0 0.8rem; }
.label { font-size: 0.85rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--muted); margin: 1.2rem 0 0.4rem; }
article.record { padding: 1rem 0 0.4rem; }
article.record + article.record { margin-top: 0.8rem; padding-top: 1.4rem;
  border-top: 1px solid var(--line); }
.record-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.2rem 0.7rem;
  margin-bottom: 0.6rem; }
.key { font-weight: 600; overflow-wrap: anywhere; }
.relation { font-size: 0.85rem; color: var(--other); }
.rel-supports { color: var(--supports); }
.rel-partially_supports { color: var(--partial); }
.rel-contrasts { color: var(--contrasts); }
blockquote, .anchor { margin: 0.8rem 0; padding: 0 0 0 1rem; border-left: 2px solid var(--line);
  color: var(--muted); font-family: Georgia, "Times New Roman", serif; font-size: 1rem;
  font-style: italic; line-height: 1.6; }
mark { background: none; color: inherit; font-style: inherit;
  text-decoration: underline 2px var(--accent); text-underline-offset: 0.2em; }
.justification, .note { margin: 0.6rem 0; }
.note { color: var(--muted); font-size: 0.85rem; }
.more { margin-top: 0.7rem; font-size: 0.85rem; color: var(--muted); }
.claim-part .meta, .more .meta { display: grid; grid-template-columns: max-content 1fr;
  gap: 0.2rem 1rem; margin: 0.6rem 0; }
.more .meta { margin: 0; padding-top: 0.6rem; border-top: 1px dashed var(--line); }
.claim-part .meta div, .more .meta div { display: contents; }
.claim-part .meta dd, .more .meta dd { color: var(--text); opacity: 0.8; min-width: 0;
  line-break: anywhere; }
.toc { margin: 2rem 0 0; }
.toc ul { list-style: none; margin: 0; padding: 0; }
.toc li { display: flex; align-items: center; gap: 0.3rem; font-size: 0.85rem;
  padding: 0.2rem 0; border-bottom: 1px solid var(--line); }
.toc a { display: flex; gap: 0.5rem; min-width: 0; flex: 1; color: var(--text);
  text-decoration: none; }
.toc a:hover .toc-text { text-decoration: underline; }
.toc-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dot { width: 0.5rem; height: 0.5rem; border-radius: 50%; flex: none; background: var(--other); }
.dot.rel-supports { background: var(--supports); }
.dot.rel-partially_supports { background: var(--partial); }
.dot.rel-contrasts { background: var(--contrasts); }
.up { float: right; font-size: 0.85rem; color: var(--muted); text-decoration: none; }
.up:hover { text-decoration: underline; }
.withdrawn { color: var(--contrasts); font-weight: 600; }
@media (max-width: 40rem) {
  main { padding: 1.5rem 0.75rem 3rem; }
  .claim-part { padding: 1.1rem 1rem 0.6rem; }
  .evidence { padding: 0.3rem 1rem 1rem; }
}
@media print {
  :root { --bg: #fff; --card: #fff; --text: #000; --muted: #444;
    --line: #999; --accent: #000; }
  body { font-size: 10.5pt; }
  main { max-width: none; padding: 0; }
  section.claim { border-color: var(--line); }
  .evidence { border-top: 1px solid var(--line); }
  article.record { break-inside: avoid; }
  .claim-text, .label { break-after: avoid; }
  a { color: #000; text-decoration: none; }
  a[href]::after { content: " (" attr(href) ")"; }
}
"""


def _e(value: object) -> str:
    return escape(str(value))


def _link(href: str, label: str) -> str:
    # Ledgers can be edited outside the server, so escaping alone is insufficient.
    try:
        scheme = urlsplit(href).scheme.lower()
    except ValueError:
        return _e(label)
    if scheme not in {"http", "https"}:
        return _e(label)
    return f'<a href="{_e(href)}">{_e(label)}</a>'


def _meta(rows: list[tuple[str, str]]) -> str:
    items = "".join(f"<div><dt>{_e(k)}</dt><dd>{v}</dd></div>" for k, v in rows if v)
    return f'<dl class="meta">{items}</dl>' if items else ""


def _identifiers(record: Record) -> str:
    parts = []
    if "doi" in record:
        parts.append("doi " + _link(f"https://doi.org/{record['doi']}", str(record["doi"])))
    if "url" in record:
        parts.append(_link(str(record["url"]), str(record["url"])))
    if "isbn" in record:
        parts.append("isbn " + _e(record["isbn"]))
    return "; ".join(parts)


def _locator(record: Record) -> str:
    loc = record.get("locator")
    if not isinstance(loc, dict):
        return ""
    return ", ".join(f"{f} {_e(loc[f])}" for f in LOCATOR_FIELDS if f in loc)


def _provenance(record: Record) -> str:
    prov = record.get("provenance")
    if not isinstance(prov, dict):
        return ""
    return ", ".join(
        _e(prov[f]) for f in ("by_type", "by", "model", "date", "manuscript_rev") if f in prov
    )


def _prose(cls: str, label: str, value: object) -> str:
    return f'<p class="{cls}"><b>{label}:</b> {_e(value)}</p>' if value else ""


def _record(record: Record, key_href: str | None = None) -> str:
    relation = str(record.get("relation", ""))
    badge = (
        f'<span class="relation rel-{_e(relation)}">{_e(relation.replace("_", " "))}</span>'
        if relation
        else ""
    )
    key = _e(record.get("key", ""))
    if key_href is not None:
        key = f'<a href="{_e(key_href)}">{key}</a>'
    head = (
        f'<div class="record-head"><span class="id">{_e(record.get("id", ""))}</span>'
        f'<span class="key">{key}</span>{badge}</div>'
    )
    gone = (
        f'<p class="withdrawn">withdrawn: {_e(record["withdrawn"])}</p>'
        if "withdrawn" in record
        else ""
    )
    quote = ""
    if isinstance(text := record.get("quote"), str):
        # Underline the phrase that carries the claim, when it occurs once in the quote.
        focus = record.get("quote_focus")
        if isinstance(focus, str) and focus and text.count(focus) == 1:
            before, after = text.split(focus)
            body_html = f"{_e(before)}<mark>{_e(focus)}</mark>{_e(after)}"
        else:
            body_html = _e(text)
        quote = f"<blockquote>{body_html}</blockquote>"
    body = (
        quote
        + _prose("justification", "Why", record.get("justification"))
        + _prose("note", "Note", record.get("note"))
        + _prose("note", "No identifier reason", record.get("no_identifier_reason"))
        + _prose("note", "Quote prefix", record.get("quote_prefix"))
        + _prose("note", "Quote suffix", record.get("quote_suffix"))
        + _prose("note", "Importance reason", record.get("importance_reason"))
        + _prose("note", "Contestable reason", record.get("contestable_reason"))
    )
    meta = _meta(
        [
            ("source", _identifiers(record)),
            ("locator", _locator(record)),
            ("evidence kind", _e(record.get("evidence_kind", ""))),
            ("quote hash", _e(record.get("quote_hash", ""))),
            ("retrieved via", _e(record.get("retrieved_via", ""))),
            (
                "found via",
                ", ".join(_e(v) for v in record["found_via"].values())
                if isinstance(record.get("found_via"), dict)
                else "",
            ),
            ("Zotero link", _e(record.get("zotero_link", ""))),
            ("derived from", _e(record.get("derived_from", ""))),
            ("added by", _provenance(record)),
        ]
    )
    rid = _e(record.get("id", ""))
    more = f'<div class="more">{meta}</div>' if meta else ""
    return f'<article class="record" data-record="{rid}">{head}{gone}{body}{more}</article>'


def _anchor(anchor: object) -> str:
    """The claim as it stands in the work, its exact words marked within their context."""
    if not isinstance(anchor, dict):
        return ""
    marker = _prose("note", "Marker", anchor.get("marker"))
    if "exact" not in anchor:
        return marker
    text = (
        _e(anchor.get("prefix", ""))
        + f"<mark>{_e(anchor['exact'])}</mark>"
        + _e(anchor.get("suffix", ""))
    )
    return f'<p class="label">In the work</p>{marker}<p class="anchor">{text}</p>'


_UNMARKED: object = object()


def _claim_parts(
    claim_id: str,
    records: list[Record],
    key_hrefs: dict[str, str] | None = None,
    anchor_html: Callable[[object], str] = _anchor,
    marked: object = _UNMARKED,
) -> tuple[str, str]:
    """The claim part and the evidence part of a claim's card, as HTML.

    With `marked`, the claim's anchor is highlighted in the work itself: the claim part shows no
    anchor and a record's anchor is shown only when it differs from the marked one."""
    in_text = marked is not _UNMARKED
    first = records[0]
    anchor = first.get("anchor")
    reference = marked if in_text else anchor
    contestable = first.get("contestable")
    meta = _meta(
        [
            ("type", _e(first.get("claim_type", ""))),
            ("importance", _e(first.get("importance", ""))),
            ("contestable", "" if contestable is None else ("yes" if contestable else "no")),
        ]
    )
    n = len(records)
    label = f'<p class="label">Evidence ({n} {"source" if n == 1 else "sources"})</p>'
    body = ""
    for record in records:
        differences = "".join(
            _prose(
                "note",
                field.replace("_", " ").capitalize(),
                ("yes" if record[field] else "no") if field == "contestable" else record[field],
            )
            for field in ("claim", "claim_type", "contestable")
            if field in record and record.get(field) != first.get(field)
        )
        if record.get("anchor") != reference:
            differences += anchor_html(record.get("anchor"))
        href = (key_hrefs or {}).get(str(record.get("key", "")))
        body += differences + _record(record, href)
    head = (
        f'<p class="claim-text"><span class="id">{_e(claim_id)}</span>'
        f"{_e(first.get('claim', ''))}</p>{'' if in_text else anchor_html(anchor)}{meta}"
    )
    return head, f"{label}{body}"


def toc(groups: dict[str, list[Record]], href: str, p: str = "") -> str:
    """A list of the claims, each a link to its card with a dot per record coloured by relation;
    empty for fewer than two claims. `p` prefixes the class names."""
    if len(groups) < 2:
        return ""
    items = ""
    for cid, records in groups.items():
        dots = "".join(
            f'<span class="{p}dot {p}rel-{_e(rel)}" title="{_e(rel.replace("_", " "))}"></span>'
            for rel in (str(r.get("relation", "")) for r in records)
        )
        items += (
            f'<li><a href="#{href}{_e(cid)}"><span class="{p}id">{_e(cid)}</span>'
            f'<span class="{p}toc-text">{_e(records[0].get("claim", ""))}</span></a>{dots}</li>'
        )
    return (
        f'<nav class="{p}toc" id="{p}contents" aria-label="Claims">'
        f'<p class="{p}label">Claims</p><ul>{items}</ul></nav>'
    )


def _claim(claim_id: str, records: list[Record], up: bool = False) -> str:
    head, evidence = _claim_parts(claim_id, records)
    back = '<a class="up" href="#contents">↑ contents</a>' if up else ""
    return (
        f'<section class="claim" id="claim-{_e(claim_id)}">'
        f'<div class="claim-part">{back}{head}</div>'
        f'<div class="evidence">{evidence}</div></section>'
    )


def _group(records: list[Record]) -> dict[str, list[Record]]:
    groups: dict[str, list[Record]] = {}
    for record in records:
        groups.setdefault(str(record.get("claim_id", "")), []).append(record)
    return dict(sorted(groups.items()))


def data_script(records: list[Record], level: str) -> str:
    """The fields a reader needs to relink a copy to their own PDFs, as JSON that the browser
    does not run; anchors, notes and other fields stay out, and `<` is escaped so the data
    cannot close the script element."""
    kept = [{f: r[f] for f in RELINK_FIELDS if f in r} for r in records]
    data = json.dumps({"level": level, "records": kept}, ensure_ascii=False)
    data = data.replace("<", "\\u003c")
    return f'<script type="application/json" id="{DATA_ID}">{data}</script>'


def render(header: dict[str, Any], records: list[Record], level: str) -> str:
    work = header.get("work")
    work = work if isinstance(work, dict) else {}
    title = _e(work.get("title", "Evidence ledger"))
    groups = _group(records)
    meta = _meta(
        [
            ("work", _e(work.get("type", ""))),
            ("claims", str(len(groups))),
            ("records", str(len(records))),
            ("quotes shown", QUOTES_SHOWN[level]),
            ("schema", _e(header.get("schema_version", ""))),
            ("created", _e(header.get("created", ""))),
            ("location", _e(work.get("location", ""))),
        ]
    )
    contents = toc(groups, "claim-")
    claims = "".join(_claim(cid, recs, bool(contents)) for cid, recs in groups.items())
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="color-scheme" content="light dark">'
        f"<title>{title}: evidence ledger summary</title><style>{STYLE}</style></head>"
        f"<body><main><h1>{title}: evidence ledger summary</h1>{meta}"
        f"{_prose('note', 'Description', header.get('description'))}"
        f"{_prose('note', 'Notes', header.get('notes'))}{contents}{claims}</main>"
        f"{data_script(records, level)}</body>"
        "</html>\n"
    )


def summarize_ledger(
    path: str, out: str, level: str = "full", include_withdrawn: bool = False
) -> dict[str, Any]:
    """Write an HTML summary to a new file; refuses if the level still leaks source text."""
    if level not in export.LEVELS:
        raise ValueError(f"level must be one of {', '.join(export.LEVELS)}")
    if Path(out).resolve() == Path(path).resolve():
        raise ValueError("out must differ from the ledger file")
    header, records = ledger.read(path)
    kept = [
        export.export_record(r, level) for r in records if include_withdrawn or "withdrawn" not in r
    ]
    if problems := export.publication_problems(header, kept, records, level):
        raise ValueError("Publication check failed: " + "; ".join(problems))
    text = render(header, kept, level)
    with open(out, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {"path": out, "level": level, "records": len(kept), "claims": len(_group(kept))}
