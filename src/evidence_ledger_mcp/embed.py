"""Embed a ledger in the HTML rendering of its work: mark each anchored claim, link its evidence."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape, unescape
from pathlib import Path
from typing import Any

from evidence_ledger_mcp import export, ledger, summary
from evidence_ledger_mcp.ledger import Record

LAYOUTS = ("endnotes", "panel")

STYLE = """
:root {
  color-scheme: light;
  --el-bg: #fbfaf7; --el-fg: #1d1d1b; --el-muted: #6b6862; --el-line: #e3dfd6;
  --el-accent: #2f5d8a; --el-hl: #e7eef6; --el-hl2: #c9daec; --el-panel: #fff;
  --el-quote: #f3f0e8; --el-bad: #a23b2a; --el-ok: #2e7d4f; --el-part: #9a6a00;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --el-bg: #18181a; --el-fg: #e8e6e1; --el-muted: #9a978f; --el-line: #33322f;
    --el-accent: #8ab4e0; --el-hl: #22303f; --el-hl2: #2f4760; --el-panel: #202023;
    --el-quote: #29292c; --el-bad: #e58a78; --el-ok: #5cc489; --el-part: #e0b040;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --el-bg: #18181a; --el-fg: #e8e6e1; --el-muted: #9a978f; --el-line: #33322f;
  --el-accent: #8ab4e0; --el-hl: #22303f; --el-hl2: #2f4760; --el-panel: #202023;
  --el-quote: #29292c; --el-bad: #e58a78; --el-ok: #5cc489; --el-part: #e0b040;
}
body { background: var(--el-bg); color: var(--el-fg); }
body a { color: var(--el-accent); }
mark.el-claim { background: var(--el-hl); color: inherit; border-radius: 2px; padding: 0 1px;
  border-bottom: 1px dotted var(--el-accent); }
mark.el-claim.el-on, mark.el-claim:hover { background: var(--el-hl2); }
mark.el-claim:focus-visible { outline: 2px solid var(--el-accent); }
sup.el-ref { font: 600 0.68em/0 system-ui, -apple-system, "Segoe UI", sans-serif;
  vertical-align: 0.5em; margin-left: 0.15em; white-space: nowrap; }
.el-hint { font: 13px/1.4 system-ui, -apple-system, "Segoe UI", sans-serif;
  color: var(--el-muted); margin: 0.5rem 1rem; }
.el-evidence { margin-top: 3rem; }
.el-card { background: var(--el-panel); color: var(--el-fg); border: 1px solid var(--el-line);
  border-radius: 10px; margin: 1rem 0; overflow: hidden; text-align: left;
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
.el-card a { color: var(--el-accent); }
.el-card p, .el-card dl, .el-card dd { margin: 0; }
.el-claim-part { padding: 1.1rem 1.3rem 0.6rem; }
.el-ev { border-top: 1px solid var(--el-line); padding: 0.3rem 1.3rem 1rem; }
.el-claim-text { font-size: 1.15rem; font-weight: 600; line-height: 1.45; margin: 0 0 0.6rem; }
.el-id { font-weight: 600; font-size: 0.85rem; color: var(--el-muted); margin-right: 0.5rem; }
.el-meta { display: grid; grid-template-columns: max-content 1fr; gap: 0.2rem 1rem;
  margin: 0.6rem 0; font-size: 0.85rem; color: var(--el-muted); }
.el-meta div { display: contents; }
.el-meta dd { color: var(--el-fg); opacity: 0.8; min-width: 0; line-break: anywhere; }
.el-more { margin-top: 0.7rem; }
.el-more .el-meta { margin: 0; padding-top: 0.6rem; border-top: 1px dashed var(--el-line); }
.el-label { font-size: 0.85rem; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--el-muted); margin: 1rem 0 0.3rem; }
.el-record { padding: 0.8rem 0 0.3rem; }
.el-record + .el-record { margin-top: 0.6rem; padding-top: 1.2rem;
  border-top: 1px solid var(--el-line); }
.el-record-head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 0.2rem 0.7rem;
  margin-bottom: 0.6rem; }
.el-key { font-weight: 600; overflow-wrap: anywhere; }
.el-relation { font-size: 0.85rem; color: var(--el-muted); }
.el-rel-supports { color: var(--el-ok); }
.el-rel-partially_supports { color: var(--el-part); }
.el-relation.el-rel-contrasts, .el-withdrawn { color: var(--el-bad); }
.el-withdrawn { font-weight: 600; }
.el-card blockquote.el-quote, .el-anchor { margin: 0.8rem 0; padding: 0 0 0 1rem;
  border: 0; border-left: 2px solid var(--el-line); background: none; color: var(--el-muted);
  font: italic 1rem/1.6 Georgia, "Times New Roman", serif; }
.el-card mark.el-hl, .el-card .el-quote mark { background: none; color: inherit;
  font-style: inherit; text-decoration: underline 2px var(--el-accent);
  text-underline-offset: 0.2em; border: 0; padding: 0; }
.el-justification, .el-text-note { margin: 0.6rem 0; }
.el-text-note { color: var(--el-muted); font-size: 0.85rem; }
.el-toc { margin: 0 0 1.5rem; font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif; }
.el-toc ul { list-style: none; margin: 0; padding: 0; }
.el-toc li { display: flex; align-items: center; gap: 0.3rem; font-size: 0.85rem;
  padding: 0.2rem 0; border-bottom: 1px solid var(--el-line); }
.el-toc a { display: flex; gap: 0.5rem; min-width: 0; flex: 1; color: var(--el-fg);
  text-decoration: none; }
.el-toc a:hover .el-toc-text { text-decoration: underline; }
.el-toc-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.el-dot { width: 0.5rem; height: 0.5rem; border-radius: 50%; flex: none;
  background: var(--el-muted); }
.el-dot.el-rel-supports { background: var(--el-ok); }
.el-dot.el-rel-partially_supports { background: var(--el-part); }
.el-dot.el-rel-contrasts { background: var(--el-bad); }
.el-back { margin: 0; padding: 0.8rem 1.3rem 0; font-size: 0.85rem; }
@media print {
  :root:root:root { color-scheme: light; --el-bg: #fff; --el-fg: #000; --el-muted: #444;
    --el-line: #999; --el-accent: #000; --el-hl: transparent; --el-hl2: transparent;
    --el-panel: #fff; --el-quote: #fff; --el-bad: #000; }
  mark.el-claim { background: none; font-weight: 700; text-decoration: underline; border: 0; }
  #el-card, .el-hint { display: none !important; }
  html { padding-right: 0 !important; }
  html.el-open body { padding-bottom: 0 !important; }
  .el-record { break-inside: avoid; }
  .el-evidence > h2, .el-claim-text, .el-label { break-after: avoid; }
  .el-card a { color: #000; text-decoration: none; }
  .el-card a[href^="http"]::after { content: " (" attr(href) ")"; }
}
"""

# Panel layout only: the text keeps clear of a fixed side panel (a bottom sheet when narrow).
PANEL_STYLE = """
mark.el-claim { scroll-margin-top: 4rem; }
html.el-panel mark.el-claim { cursor: pointer; }
html:not(.el-panel) #el-card, html:not(.el-panel) .el-howto { display: none; }
.el-toggle { font: inherit; color: var(--el-accent); background: none; cursor: pointer;
  border: 1px solid var(--el-line); border-radius: 4px; padding: 0 0.5rem; margin-left: 0.5rem; }
#el-card { position: fixed; left: 0; right: 0; bottom: 0; max-height: 70vh; z-index: 2000;
  overflow-y: auto; background: var(--el-panel); color: var(--el-fg);
  border-top: 1px solid var(--el-line); border-radius: 12px 12px 0 0;
  box-shadow: 0 -6px 24px rgba(0, 0, 0, 0.18); padding: 0.8rem 1rem 1.2rem;
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
#el-card[hidden] { display: none; }
#el-card:focus { outline: none; }
#el-card header { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem;
  color: var(--el-muted); font-size: 0.8rem; margin-bottom: 0.5rem; }
#el-card header button { background: none; color: var(--el-fg); border: 1px solid var(--el-line);
  border-radius: 6px; padding: 0.15rem 0.5rem; cursor: pointer; font: inherit; }
#el-card .el-card { border: 0; background: none; margin: 0; border-radius: 0; overflow: visible; }
#el-card .el-claim-part, #el-card .el-ev { padding-left: 0; padding-right: 0; }
html.el-open body { padding-bottom: 70vh; }
@media screen {
  /* With the panel working, located claims are read there; the end cards remain for print. */
  html.el-panel .el-evidence > .el-card:has(.el-back),
  html.el-panel .el-evidence > .el-toc, html.el-panel .el-evidence:not(:has(h3)) {
    display: none; }
}
@media (min-width: 900px) {
  html.el-panel { padding-right: clamp(300px, 36vw, 420px); }
  html.el-open body { padding-bottom: 0; }
  .el-esc { display: none; }
  #el-card { left: auto; top: 0; bottom: 0; right: 0; width: clamp(300px, 36vw, 420px);
    max-height: none; border: 0; border-left: 1px solid var(--el-line); border-radius: 0;
    box-shadow: none;
    padding: 1rem; }
  #el-card button[data-el="0"] { display: none; }
}
"""

SCRIPT = """
(function () {
  var panel = document.getElementById("el-card");
  if (!panel) return;
  var title = panel.querySelector(".el-panel-title");
  var body = panel.querySelector(".el-panel-body");
  var marks = [].slice.call(document.querySelectorAll("mark.el-claim"));
  var hint = document.querySelector(".el-hint");
  var root = document.documentElement;
  var current = null;
  var wide = matchMedia("(min-width: 900px)");
  var toggle = document.querySelector(".el-toggle");
  var mode = panel.dataset.layout;
  try { mode = localStorage.getItem("el-layout") || mode; } catch (e) { /* storage blocked */ }
  function first(mark) {
    return marks.filter(function (m) { return m.dataset.claim === mark.dataset.claim; })[0];
  }
  var firsts = marks.filter(function (m) { return first(m) === m; });
  firsts.forEach(function (m) {
    m.setAttribute("tabindex", "0");
    m.setAttribute("role", "button");
    m.setAttribute("aria-controls", "el-card");
    m.setAttribute("aria-expanded", "false");
  });
  if (hint) hint.hidden = false;
  root.classList.add("el-js");
  function unmark() {
    marks.forEach(function (m) { m.classList.remove("el-on"); });
    firsts.forEach(function (m) { m.setAttribute("aria-expanded", "false"); });
  }
  function show(clicked, scroll, focus) {
    var mark = first(clicked);
    var id = mark.dataset.claim;
    var source = document.getElementById("el-" + id);
    if (!source) return;
    var copy = source.cloneNode(true);
    copy.removeAttribute("id");
    [].forEach.call(copy.querySelectorAll("[id]"), function (n) { n.removeAttribute("id"); });
    [].forEach.call(copy.querySelectorAll(".el-back"), function (n) { n.remove(); });
    body.textContent = "";
    body.appendChild(copy);
    unmark();
    current = mark;
    marks.forEach(function (m) { if (m.dataset.claim === id) m.classList.add("el-on"); });
    mark.setAttribute("aria-expanded", "true");
    title.textContent = id + " (passage " + (firsts.indexOf(mark) + 1) + " of "
      + firsts.length + ")";
    panel.hidden = false;
    panel.scrollTop = 0;
    root.classList.add("el-open");
    if (scroll) {
      clicked.scrollIntoView(
        { block: innerWidth >= 900 ? "nearest" : "start", behavior: "smooth" });
    }
    if (focus !== false) panel.focus({ preventScroll: true });
  }
  function close() {
    // On wide screens the panel stays open as a sidebar.
    if (!current || wide.matches) return;
    var mark = current;
    current = null;
    unmark();
    panel.hidden = true;
    root.classList.remove("el-open");
    mark.focus({ preventScroll: true });
  }
  function setMode(m, remember) {
    mode = m === "panel" ? "panel" : "endnotes";
    root.classList.toggle("el-panel", mode === "panel");
    if (toggle) toggle.textContent = mode === "panel" ? "Show as endnotes" : "Show in side panel";
    if (remember) {
      try { localStorage.setItem("el-layout", mode); } catch (e) { /* storage blocked */ }
    }
    if (mode === "panel") return widen();
    current = null;
    unmark();
    panel.hidden = true;
    root.classList.remove("el-open");
  }
  function step(d) {
    var i = firsts.indexOf(current);
    show(firsts[(i + d + firsts.length) % firsts.length], true);
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest(".el-toggle")) {
      return setMode(mode === "panel" ? "endnotes" : "panel", true);
    }
    if (mode !== "panel") return;
    var ref = e.target.closest("sup.el-ref a");
    var mark = e.target.closest("mark.el-claim")
      || (ref && firsts.filter(function (m) {
        return "#el-" + m.dataset.claim === ref.getAttribute("href");
      })[0]);
    if (mark) {
      // A real link inside a mark keeps its own behaviour.
      if (!ref && e.target.closest("a")) return;
      e.preventDefault();
      return show(mark, innerWidth < 900);
    }
    var button = e.target.closest("#el-card button");
    if (button) return button.dataset.el === "0" ? close() : step(+button.dataset.el);
    if (current && !e.target.closest("#el-card")) close();
  });
  document.addEventListener("keydown", function (e) {
    if (mode !== "panel") return;
    var target = e.target;
    var mark = target.closest && target.closest("mark.el-claim");
    if (mark && target === mark && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      show(mark, false);
    } else if (e.key === "Escape") {
      close();
    } else if (current && (e.key === "ArrowRight" || e.key === "ArrowLeft")
        && !e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey
        && !(target.closest && target.closest(
          "pre, code, table, input, textarea, select, "
          + "[contenteditable]:not([contenteditable='false'])"))) {
      e.preventDefault();
      step(e.key === "ArrowRight" ? 1 : -1);
    }
  });
  function widen() {
    if (mode === "panel" && wide.matches && firsts.length) {
      show(current || firsts[0], false, false);
    }
  }
  if (wide.addEventListener) wide.addEventListener("change", widen);
  else if (wide.addListener) wide.addListener(widen);
  setMode(mode, false);
})();
"""

PANEL = (
    '<aside id="el-card" hidden data-layout="{layout}" tabindex="-1" role="dialog" '
    'aria-label="Evidence">'
    '<header><span class="el-panel-title"></span><span>'
    '<button type="button" data-el="-1" aria-label="Previous passage">&larr;</button> '
    '<button type="button" data-el="1" aria-label="Next passage">&rarr;</button> '
    '<button type="button" data-el="0" aria-label="Close">&#10005;</button>'
    '</span></header><div class="el-panel-body"></div></aside>'
)
HINT = (
    '<p class="el-hint" hidden><span class="el-howto">Click or press Enter on a highlighted '
    "passage to see its evidence; &larr; &rarr; step through the passages."
    '<span class="el-esc"> Esc closes the panel.</span></span>'
    '<button type="button" class="el-toggle"></button></p>'
)

_CLASS_NAMES = {"evidence": "el-ev", "note": "el-text-note"}
_TOKEN = re.compile(
    r"<!--.*?-->"
    r"|<(script|style)\b(?:[^>\"']|\"[^\"]*\"|'[^']*')*>.*?</\1\s*>"
    r"|<![^>]*>|<\?.*?\?>"
    r"|</?[A-Za-z](?:[^>\"']|\"[^\"]*\"|'[^']*')*>",
    re.S | re.I,
)
_PIECE = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);|.", re.S)
_TAG_NAME = re.compile(r"</?([A-Za-z][^\s/>]*)")
_REF_ID = re.compile(r"""\bid\s*=\s*(?:"ref-([^"]+)"|'ref-([^']+)')""", re.I)
_OPEN = r"(?:[^>\"']|\"[^\"]*\"|'[^']*')*>"
_HTML_OPEN = re.compile(r"<html\b" + _OPEN, re.I)
_HEAD_OPEN = re.compile(r"<head\b" + _OPEN, re.I)
_BODY_OPEN = re.compile(r"<body\b" + _OPEN, re.I)
_BASE = re.compile(r"<base\b[^>]*\bhref\s*=", re.I)
_HEAD_CLOSE = re.compile(r"</head\s*>", re.I)
_BODY_CLOSE = re.compile(r"</body\s*>", re.I)
_META = re.compile(r"<meta\b" + _OPEN, re.I)
_CHARSET = re.compile(r"(charset\s*=\s*[\"']?)\s*([^\s\"'>;/]+)", re.I)
_DASHES = re.compile(r"-{2,3}")
# Typography that differs between the ledger's quote and the rendered work.
_TYPO = {
    **dict.fromkeys(range(0x2018, 0x201C), "'"),  # single curly quotes
    **dict.fromkeys(range(0x201C, 0x2020), '"'),  # double curly quotes
    **dict.fromkeys(range(0x2010, 0x2016), "-"),  # hyphens and dashes
    0x2026: "...",
}
VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
    "source", "track", "wbr",
}  # fmt: skip
SEPARATORS = {
    "p", "li", "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "td", "figcaption", "div",
    "br", "hr", "section", "article", "ul", "ol", "table", "tr", "th", "dt", "dd", "pre",
    "figure", "header", "footer", "main", "aside", "nav",
}  # fmt: skip
HEAD_ELEMENTS = {"title", "meta", "link", "style", "script", "base", "noscript", "template"}
SKIP_TEXT = {"textarea", "title", "svg", "math", "template", "noscript", "select", "option"}

Segments = list[tuple[int, int, int]]
Taken = dict[int, list[tuple[int, int, str]]]


@dataclass
class _Char:
    token: int
    start: int
    end: int


@dataclass
class _Doc:
    tokens: list[str]
    is_text: list[bool]
    text: str = ""
    chars: list[_Char | None] = field(default_factory=list)
    link_end: dict[int, int] = field(default_factory=dict)  # text token -> its </a> token


def _split(html: str) -> tuple[list[str], list[bool]]:
    tokens: list[str] = []
    is_text: list[bool] = []
    pos = 0
    for match in _TOKEN.finditer(html):
        if match.start() > pos:
            tokens.append(html[pos : match.start()])
            is_text.append(True)
        tokens.append(match.group())
        is_text.append(False)
        pos = match.end()
    if pos < len(html):
        tokens.append(html[pos:])
        is_text.append(True)
    return tokens, is_text


def _norm(value: str) -> str:
    """Typography normalised and whitespace collapsed, as the work's text is."""
    return " ".join(_DASHES.sub("-", value.translate(_TYPO)).split())


def _merge(refs: list[_Char]) -> _Char | None:
    if not refs:
        return None
    if all(r.token == refs[0].token for r in refs):
        return _Char(refs[0].token, min(r.start for r in refs), max(r.end for r in refs))
    return refs[0]


def _parse(html: str) -> _Doc:
    """Tokenize and collect the visible text (typography normalised, whitespace collapsed)."""
    tokens, is_text = _split(html)
    doc = _Doc(tokens, is_text)
    text: list[str] = []
    chars: list[_Char | None] = []
    in_head = False
    skip: list[str] = []
    link_texts: list[int] | None = None

    def add(char: str, ref: _Char | None) -> None:
        if char.isspace():
            if text and text[-1] == " ":
                return
            char = " "
        text.append(char)
        chars.append(ref)

    for index, raw in enumerate(tokens):
        if is_text[index]:
            if link_texts is not None:
                link_texts.append(index)
            if in_head or skip:
                continue
            offset = 0
            for piece in _PIECE.finditer(raw):
                ref = _Char(index, piece.start(), piece.end())
                for char in unescape(piece.group()) if len(piece.group()) > 1 else piece.group():
                    for mapped in char.translate(_TYPO):
                        add(mapped, ref)
                offset = piece.end()
            assert offset == len(raw)
            continue
        match = _TAG_NAME.match(raw)
        if match is None:
            continue
        name = match.group(1).lower()
        if name in SEPARATORS and text and text[-1] != " ":
            add(" ", None)
        if raw.startswith("</"):
            if name == "head":
                in_head = False
            elif name == "a" and link_texts is not None:
                for t in link_texts:
                    doc.link_end[t] = index
                link_texts = None
            if name in skip:
                del skip[len(skip) - 1 - skip[::-1].index(name) :]
            continue
        if in_head and name not in HEAD_ELEMENTS and name != "head":
            in_head = False  # a head that was never closed
        if name in VOID or raw.endswith("/>"):
            continue
        if name == "head":
            in_head = True
        elif name == "a":
            link_texts = []
        if name == "option" and skip[-1:] == ["option"]:
            skip.pop()  # its end tag is optional
        if name in SKIP_TEXT:
            skip.append(name)
    joined = "".join(text)
    parts: list[str] = []
    out_chars: list[_Char | None] = []
    pos = 0
    for run in _DASHES.finditer(joined):
        parts.append(joined[pos : run.start()])
        out_chars.extend(chars[pos : run.start()])
        parts.append("-")
        out_chars.append(_merge([c for c in chars[run.start() : run.end()] if c is not None]))
        pos = run.end()
    parts.append(joined[pos:])
    out_chars.extend(chars[pos:])
    doc.text = "".join(parts)
    doc.chars = out_chars
    return doc


def reference_keys(html: str) -> set[str]:
    """The keys of the work's `id="ref-<key>"` bibliography entries."""
    return {unescape(a or b) for a, b in _REF_ID.findall(html)}


def _occurrences(text: str, needle: str) -> list[int]:
    found = []
    start = text.find(needle)
    while start != -1:
        found.append(start)
        start = text.find(needle, start + 1)
    return found


def _score(text: str, start: int, end: int, anchor: dict[str, Any]) -> int:
    score = 0
    prefix = _norm(str(anchor.get("prefix", "")))
    suffix = _norm(str(anchor.get("suffix", "")))
    if prefix and text[:start].rstrip().endswith(prefix):
        score += 1
    if suffix and text[end:].lstrip().startswith(suffix):
        score += 1
    # A hit on word boundaries beats a hit inside a longer word, whatever the context says.
    left = start == 0 or not (text[start - 1].isalnum() and text[start].isalnum())
    right = end == len(text) or not (text[end - 1].isalnum() and text[end].isalnum())
    return score + 4 * (left and right)


def _candidates(doc: _Doc, anchor: object) -> list[Segments]:
    """Segments (token, start, end) of every occurrence of `anchor['exact']`, best first."""
    if not isinstance(anchor, dict) or not isinstance(anchor.get("exact"), str):
        return []
    needle = _norm(anchor["exact"])
    if not needle:
        return []
    spans = [(s, s + len(needle)) for s in _occurrences(doc.text, needle)]
    found: list[Segments] = []
    for start, end in sorted(spans, key=lambda s: -_score(doc.text, s[0], s[1], anchor)):
        bounds: dict[int, list[int]] = {}
        for ref in doc.chars[start:end]:
            if ref is not None:
                low_high = bounds.setdefault(ref.token, [ref.start, ref.end])
                low_high[0], low_high[1] = min(low_high[0], ref.start), max(low_high[1], ref.end)
        if bounds:
            found.append([(token, low, high) for token, (low, high) in sorted(bounds.items())])
    return found


def _blocker(segments: Segments, taken: Taken) -> str | None:
    """The claim whose marked text overlaps `segments`, if any."""
    for token, low, high in segments:
        for a, b, claim_id in taken.get(token, []):
            if not (high <= a or low >= b):
                return claim_id
    return None


def locate(doc: _Doc, anchor: object, taken: Taken) -> Segments | None:
    """Segments of the best occurrence of `anchor['exact']` not overlapping `taken`, or None."""
    return next((c for c in _candidates(doc, anchor) if _blocker(c, taken) is None), None)


def _prefixed(html: str) -> str:
    def rename(match: re.Match[str]) -> str:
        names = (_CLASS_NAMES.get(n, f"el-{n}") for n in match.group(1).split())
        return f'class="{" ".join(names)}"'

    html = re.sub(r'class="([^"]*)"', rename, html)
    return html.replace("<blockquote>", '<blockquote class="el-quote">').replace(
        "<mark>", '<mark class="el-hl">'
    )


def _bare(anchor: object, note: str) -> str:
    """An anchor without the work's text: the marker, and a note when there was text."""
    if not isinstance(anchor, dict):
        return ""
    out = summary._prose("note", "Marker", anchor.get("marker"))
    return out + (f'<p class="note">{note}</p>' if "exact" in anchor else "")


def _card(
    claim_id: str,
    records: list[Record],
    key_hrefs: dict[str, str],
    level: str,
    marked: object = summary._UNMARKED,
    note: str = "",
) -> str:
    """One claim's card; `marked` is the anchor highlighted in the work, if it was located."""
    located = marked is not summary._UNMARKED
    anchors: Callable[[object], str] = (
        summary._anchor
        if level == "full"
        else lambda a: _bare(
            a, "Anchor text withheld at this level." if located else "Text not found in the work."
        )
    )
    head, evidence = summary._claim_parts(claim_id, records, key_hrefs, anchors, marked)
    cid = escape(claim_id)
    back = (
        f'<p class="back"><a href="#el-back-{cid}">&#8617; back to text</a></p>' if located else ""
    )
    inner = _prefixed(
        f'{back}<div class="claim-part">{head}</div><div class="evidence">{evidence}</div>'
    )
    if note:
        inner = f'<p class="el-text-note el-claim-part">{escape(note)}</p>{inner}'
    return f'<section class="el-card" id="el-{cid}">{inner}</section>'


def _tags(html: str, pattern: re.Pattern[str]) -> list[re.Match[str]]:
    """Matches of `pattern` that are real tags, not text inside comments, scripts or styles."""
    found = []
    for token in _TOKEN.finditer(html):
        if match := pattern.match(html, token.start(), token.end()):
            found.append(match)
    return found


def _first(html: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
    return next(iter(_tags(html, pattern)), None)


def _utf8(html: str) -> str:
    """Declare utf-8, the encoding of the output: fix a declared charset, or add one to a head."""
    body = _first(html, _BODY_OPEN)
    limit = body.start() if body else len(html)
    found = False
    tags = {m.start() for m in _tags(html, _META)}

    def fix(match: re.Match[str]) -> str:
        nonlocal found
        if match.start() >= limit or match.start() not in tags:
            return match.group()
        if not _CHARSET.search(match.group()):
            return match.group()
        found = True
        return _CHARSET.sub(lambda c: c.group(1) + "utf-8", match.group(), count=1)

    html = _META.sub(fix, html)
    head = _first(html, _HEAD_OPEN)
    if not found and head:
        return html[: head.end()] + '<meta charset="utf-8">' + html[head.end() :]
    return html


def _inject(html: str, head_html: str) -> str:
    """Put `head_html` before </head>, creating a head if the work has none."""
    head = _first(html, _HEAD_CLOSE)
    if head:
        return html[: head.start()] + head_html + html[head.start() :]
    opening = _first(html, _HTML_OPEN) or re.match(r"\s*<!doctype[^>]*>", html, re.I)
    new = f'<head><meta charset="utf-8">{head_html}</head>'
    if opening:
        return html[: opening.end()] + new + html[opening.end() :]
    return new + html


def _wrap_body(html: str, before: str, after: str) -> str:
    """Put `before` right after <body> and `after` before </body>, or around the whole text."""
    # Without a <body> tag, the body starts after the head (or <html>, or the doctype).
    opening = (
        _first(html, _BODY_OPEN)
        or _first(html, _HEAD_CLOSE)
        or _first(html, _HTML_OPEN)
        or re.match(r"\s*<!doctype[^>]*>", html, re.I)
    )
    at = opening.end() if opening else 0
    html = html[:at] + before + html[at:]
    closing = _tags(html, _BODY_CLOSE)
    if closing:
        at = closing[-1].start()
        return html[:at] + after + html[at:]
    return html + after


def embed(
    work_html: str, header: dict[str, Any], records: list[Record], layout: str, level: str = "full"
) -> tuple[str, list[str], list[str], dict[str, str]]:
    """The work with its claims marked and linked; also the located and unlocated claim ids and
    the claims left unlocated because their text is already marked for another claim."""
    doc = _parse(work_html)
    del header  # the work's own title and metadata stay as rendered
    groups = summary._group(records)
    refs = reference_keys(work_html)
    key_hrefs = {
        str(r["key"]): f"#ref-{r['key']}" for r in records if f"{r.get('key', '')}" in refs
    }
    taken: Taken = {}
    edits: dict[int, list[tuple[int, int, str, bool]]] = {}
    marked: dict[str, object] = {}
    overlapping: dict[str, str] = {}
    for claim_id, group in groups.items():
        blocked: str | None = None
        for record in group:
            candidates = _candidates(doc, record.get("anchor"))
            segments = next((c for c in candidates if _blocker(c, taken) is None), None)
            if segments is None:
                blocked = blocked or (_blocker(candidates[0], taken) if candidates else None)
                continue
            for n, (token, low, high) in enumerate(segments):
                taken.setdefault(token, []).append((low, high, claim_id))
                edits.setdefault(token, []).append((low, high, claim_id, n == len(segments) - 1))
            marked[claim_id] = record.get("anchor")
            break
        else:
            if blocked:
                overlapping[claim_id] = blocked
    located = list(marked)

    out: list[str] = []
    after: dict[int, list[str]] = {}
    for index, raw in enumerate(doc.tokens):
        pos = 0
        for low, high, claim_id, last in sorted(edits.get(index, [])):
            cid = escape(claim_id)
            out.append(raw[pos:low])
            out.append(f'<mark class="el-claim" data-claim="{cid}">{raw[low:high]}</mark>')
            if last:
                sup = f'<sup class="el-ref"><a href="#el-{cid}" id="el-back-{cid}">{cid}</a></sup>'
                end = doc.link_end.get(index)  # after the link that holds the text, not inside it
                if end is None:
                    out.append(sup)
                else:
                    after.setdefault(end, []).append(sup)
            pos = high
        out.append(raw[pos:])
        out.extend(after.pop(index, []))
    body = "".join(out)

    missing = [cid for cid in groups if cid not in marked]
    parts = [_card(cid, groups[cid], key_hrefs, level, marked[cid]) for cid in located]
    if missing:
        parts.append("<h3>Not located in the work</h3>")
        parts.extend(
            _card(
                cid,
                groups[cid],
                key_hrefs,
                level,
                note=f"Anchor text overlaps {overlapping[cid]}." if cid in overlapping else "",
            )
            for cid in missing
        )
    section = (
        f'<section class="el-evidence" id="el-evidence"><h2>Evidence</h2>'
        f"{summary.toc(groups, 'el-', 'el-')}{''.join(parts)}</section>"
    )
    # Both views are always written; `layout` picks the one a reader sees first.
    panel = bool(located)
    style = f"<style>{STYLE}{PANEL_STYLE if panel else ''}</style>"
    if panel:
        section += f"{PANEL.replace('{layout}', layout)}<script>{SCRIPT}</script>"
    section += summary.data_script(records, level)
    body = _wrap_body(body, HINT if panel else "", section)
    return _inject(_utf8(body), style), located, missing, overlapping


def embed_ledger(
    path: str,
    work: str,
    out: str,
    level: str = "full",
    layout: str = "endnotes",
    include_withdrawn: bool = False,
) -> dict[str, Any]:
    """Write the work's HTML with its ledger embedded to a new file; refuses on a leaky level."""
    if level not in export.LEVELS:
        raise ValueError(f"level must be one of {', '.join(export.LEVELS)}")
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {', '.join(LAYOUTS)}")
    target = Path(out).resolve()
    if target == Path(path).resolve():
        raise ValueError("out must differ from the ledger file")
    if target == Path(work).resolve():
        raise ValueError("out must differ from the work file")
    # Relative links to figures, styles and scripts resolve against the work's folder.
    if target.parent != Path(work).resolve().parent:
        raise ValueError("out must be in the same folder as the work, so relative links still work")
    header, records = ledger.read(path)
    kept = [
        export.export_record(r, level) for r in records if include_withdrawn or "withdrawn" not in r
    ]
    if problems := export.publication_problems(header, kept, records, level):
        raise ValueError("Publication check failed: " + "; ".join(problems))
    html = Path(work).read_text("utf-8")
    if _first(html, _BASE):
        raise ValueError("the work sets <base href>, which would send evidence links elsewhere")
    text, located, missing, overlapping = embed(html, header, kept, layout, level)
    with open(out, "x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return {
        "path": out,
        "level": level,
        "layout": "panel" if layout == "panel" and located else "endnotes",
        "records": len(kept),
        "claims": len(located) + len(missing),
        "located": len(located),
        "not_located": missing,
        "overlapping": overlapping,
    }
