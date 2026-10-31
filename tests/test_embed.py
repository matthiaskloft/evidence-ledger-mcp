from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import embed, ledger

WORK = {"title": "Example work", "type": "manuscript"}
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
QUOTE = "Ledger records reduced unchecked citations from 40 to 3 per manuscript"
RECORD: dict[str, Any] = {
    "claim": "Ledgers cut unchecked citations.",
    "claim_type": "empirical",
    "contestable": True,
    "anchor": {"exact": "cut unchecked citations"},
    "key": "exampleStudy2026",
    "doi": "10.1000/example",
    "locator": {"page": 4},
    "quote": QUOTE,
    "relation": "supports",
    "justification": "The quoted sentence states both counts.",
    "retrieved_via": "pdf",
}
HTML = (
    "<!DOCTYPE html><html><head><title>cut unchecked citations</title>"
    "<style>p { color: red }</style></head><body>"
    "<p>Our tool did <em>cut unchecked</em> citations&nbsp;in\n  trials.</p>"
    "<p>Second paragraph.</p>"
    '<div id="refs"><div id="ref-exampleStudy2026">Example (2026).</div></div>'
    "</body></html>"
)


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, WORK)
    return target


def add(path: str, **changes: Any) -> dict[str, Any]:
    return ledger.add_record(path, {**RECORD, **changes}, PROVENANCE)


def run(path: str, html: str = HTML, **kwargs: Any) -> tuple[dict[str, Any], str]:
    folder = Path(path).parent
    work = folder / "work.html"
    work.write_text(html, "utf-8")
    out = folder / "embedded.html"
    result = embed.embed_ledger(path, str(work), str(out), **kwargs)
    return result, out.read_text("utf-8")


def tokens_of(html: str, **anchor: Any) -> list[int]:
    segments = embed.locate(embed._parse(html), anchor, {})
    assert segments is not None
    return [token for token, _, _ in segments]


def test_matches_across_inline_tags_and_whitespace(path: str) -> None:
    add(path, anchor={"exact": "cut unchecked  citations in trials"})
    result, html = run(path)
    assert result["located"] == 1 and result["not_located"] == []
    assert html.count('<mark class="el-claim" data-claim="C-0001">') == 2
    assert '<em><mark class="el-claim" data-claim="C-0001">cut unchecked</mark></em>' in html
    assert '<mark class="el-claim" data-claim="C-0001"> citations&nbsp;in\n  trials</mark>' in html
    assert html.count('class="el-ref"') == 1
    assert html.index("trials</mark>") < html.index('<sup class="el-ref">')


def test_prefix_and_suffix_pick_the_occurrence() -> None:
    html = "<p>alpha target one</p><p>beta target two</p><p>gamma target three</p>"
    assert tokens_of(html, exact="target") == [1]
    assert tokens_of(html, exact="target", prefix="beta") == [4]
    assert tokens_of(html, exact="target", suffix="three") == [7]
    assert tokens_of(html, exact="target", prefix="nowhere") == [1]


def test_missing_and_marker_only_anchors_are_listed(path: str) -> None:
    add(path)
    add(path, claim="Marker claim.", anchor={"marker": "[2]"})
    add(path, claim="Missing claim.", anchor={"exact": "words that are not there"})
    result, html = run(path)
    assert (result["claims"], result["located"]) == (3, 1)
    assert result["not_located"] == ["C-0002", "C-0003"]
    assert html.index("Not located in the work") < html.index('id="el-C-0002"')
    assert 'id="el-back-C-0002"' not in html
    assert html.count("back to text") == 1


def test_text_in_head_and_scripts_is_not_matched() -> None:
    html = "<html><head><title>hidden words</title></head><body><script>hidden words</script>"
    assert embed.locate(embed._parse(html), {"exact": "hidden words"}, {}) is None


def test_bibliography_key_links_only_when_present(path: str) -> None:
    add(path)
    add(path, claim="Other.", key="absentKey", anchor={"exact": "Second paragraph"})
    _, html = run(path)
    assert '<a href="#ref-exampleStudy2026">exampleStudy2026</a>' in html
    assert "#ref-absentKey" not in html
    assert 'href="https://doi.org/10.1000/example"' in html


def test_endnotes_layout(path: str) -> None:
    add(path)
    result, html = run(path, layout="endnotes")
    assert result["layout"] == "endnotes"
    assert '<sup class="el-ref"><a href="#el-C-0001" id="el-back-C-0001">C-0001</a></sup>' in html
    assert '<section class="el-evidence" id="el-evidence"><h2>Evidence</h2>' in html
    assert html.index('id="el-evidence"') < html.index("</body>")
    assert 'href="#el-back-C-0001">&#8617; back to text' in html
    assert "<aside" not in html
    assert "<style>p { color: red }</style><style>" in html
    assert QUOTE in html


def test_panel_layout(path: str) -> None:
    add(path)
    add(path, claim="Second.", anchor={"exact": "Second paragraph"})
    add(path, claim="Gone.", anchor={"marker": "x"})
    result, html = run(path, layout="panel")
    assert result["not_located"] == ["C-0003"]
    assert html.count("<aside") == 1 and '<aside id="el-card" hidden' in html
    assert html.count('<mark class="el-claim"') >= 2 and "tabindex" not in html.split("<aside")[0]
    assert html.count('<section class="el-card" id="el-C-000') == 3  # the panel clones these
    assert html.index('id="el-evidence"') < html.index('id="el-card"') < html.index("</body>")
    assert 'href="#el-back-C-0001">&#8617; back to text' in html
    assert '<p class="el-hint" hidden>' in html and html.count("<script>") == 1
    assert "html.el-js { padding-right: min(400px, 32vw); }" in html and "@media print" in html
    assert "el-el-" not in html


def test_theme_is_owned_by_the_output(path: str) -> None:
    add(path)
    for layout in embed.LAYOUTS:
        _, html = run(path, layout=layout)
        Path(path).parent.joinpath("embedded.html").unlink()
        assert "body { background: var(--el-bg); color: var(--el-fg); }" in html
        assert 'dark) {\n  :root:not([data-theme="light"])' in html
        assert ':root[data-theme="dark"]' in html
        assert "background: var(--el-panel)" in html and "#1e2229" not in html


def test_endnotes_has_no_script_or_panel(path: str) -> None:
    add(path)
    _, html = run(path)
    assert "<script>" not in html and "<aside" not in html and "role=" not in html


def test_masked_and_locator_hide_quotes(path: str) -> None:
    add(path)
    _, masked = run(path, level="masked")
    assert "Ledger records" in masked and "unchecked citations from 40" not in masked
    Path(path).parent.joinpath("embedded.html").unlink()
    _, bare = run(path, level="locator")
    assert "<blockquote" not in bare and "Ledger records" not in bare


def test_leak_refuses_and_writes_nothing(path: str) -> None:
    add(path, note=f"Says: {QUOTE.upper()}!")
    out = Path(path).parent / "embedded.html"
    work = Path(path).parent / "work.html"
    work.write_text(HTML, "utf-8")
    with pytest.raises(ValueError, match="R-0001"):
        embed.embed_ledger(path, str(work), str(out), level="masked")
    assert not out.exists()


def test_refuses_overwrite_and_bad_arguments(path: str) -> None:
    add(path)
    folder = Path(path).parent
    work = folder / "work.html"
    work.write_text(HTML, "utf-8")
    out = folder / "embedded.html"
    out.write_text("keep", "utf-8")
    with pytest.raises(FileExistsError):
        embed.embed_ledger(path, str(work), str(out))
    assert out.read_text("utf-8") == "keep"
    with pytest.raises(ValueError, match="work"):
        embed.embed_ledger(path, str(work), str(work))
    with pytest.raises(ValueError, match="ledger"):
        embed.embed_ledger(path, str(work), path)
    elsewhere = folder / "sub"
    elsewhere.mkdir()
    with pytest.raises(ValueError, match="same folder"):
        embed.embed_ledger(path, str(work), str(elsewhere / "embedded.html"))
    assert not (elsewhere / "embedded.html").exists()
    with pytest.raises(ValueError, match="level"):
        embed.embed_ledger(path, str(work), str(out), level="all")
    with pytest.raises(ValueError, match="layout"):
        embed.embed_ledger(path, str(work), str(out), layout="side")
    assert work.read_text("utf-8") == HTML


def test_head_is_created_and_claims_are_escaped(path: str) -> None:
    add(path, claim="<script>alert(1)</script>")
    _, html = run(path, "<p>Plain: cut unchecked citations.</p>")
    assert html.startswith("<head><meta charset")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


LDQ, RDQ, RSQ, EN, EM, ELL = (chr(c) for c in (0x201C, 0x201D, 0x2019, 0x2013, 0x2014, 0x2026))


def run_new(path: str, html: str = HTML, **kwargs: Any) -> tuple[dict[str, Any], str]:
    Path(path).parent.joinpath("embedded.html").unlink(missing_ok=True)
    return run(path, html, **kwargs)


def test_panel_output_keeps_doctype_first_and_hint_after_body(path: str) -> None:
    add(path)
    _, html = run(path, layout="panel")
    assert html.startswith("<!DOCTYPE html><html><head>")
    assert '<body><p class="el-hint" hidden>' in html
    _, bare = run_new(path, "<!DOCTYPE html><html lang='en'><body><p>cut unchecked citations</p>")
    assert bare.startswith("<!DOCTYPE html><html lang='en'><head><meta charset=")


def test_panel_without_javascript_stays_plain(path: str) -> None:
    add(path)
    _, html = run(path, layout="panel")
    assert "role=" not in html.split("<aside")[0]
    assert "\nhtml { padding-right" not in html and "\nmark.el-claim { cursor" not in html
    assert "html.el-js mark.el-claim { cursor: pointer; }" in html
    script = html.split("<script>")[1]
    for attribute in ("tabindex", "role", "aria-controls", "aria-expanded"):
        assert f'setAttribute("{attribute}"' in script
    assert "firsts.forEach" in script  # only a claim's first mark becomes a control


def test_panel_script_handles_resize_keys_and_links(path: str) -> None:
    add(path)
    _, html = run(path, layout="panel")
    script = html.split("<script>")[1]
    assert 'wide.addEventListener("change", widen)' in script
    assert "show(current || firsts[0], false, false)" in script
    assert "!e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey" in script
    assert "pre, code, table, input, textarea, select" in script
    assert "e.preventDefault();\n      step" in script
    assert 'if (!ref && e.target.closest("a")) return;' in script


def test_hint_fits_both_widths_and_styles_cover_chrome(path: str) -> None:
    add(path)
    _, html = run(path, layout="panel")
    assert "Click or press Enter on a highlighted passage" in html
    assert '<span class="el-esc"> Esc closes the panel.</span>' in html
    assert ".el-esc { display: none; }" in html
    assert "z-index: 2000" in html
    assert "html.el-open body { padding-bottom: 0 !important; }" in html


def test_panel_without_located_claims_reports_endnotes(path: str) -> None:
    add(path, anchor={"exact": "nowhere in the work"})
    result, html = run(path, layout="panel")
    assert result["layout"] == "endnotes" and result["located"] == 0
    assert "<aside" not in html and "<script>" not in html


def test_overlapping_claims_are_reported(path: str) -> None:
    add(path, anchor={"exact": "cut unchecked"})
    add(path, claim="Overlap.", anchor={"exact": "unchecked citations"})
    result, html = run(path)
    assert result["located"] == 1 and result["not_located"] == ["C-0002"]
    assert result["overlapping"] == {"C-0002": "C-0001"}
    assert html.index("Not located in the work") < html.index("overlaps C-0001")
    assert html.count('class="el-claim"') == 1
    result, _ = run_new(path, "<p>Nothing.</p>")
    assert result["overlapping"] == {}


def test_typography_is_normalised_on_both_sides() -> None:
    html = f"<p>She said {LDQ}hello {EM} world{RDQ}; it{RSQ}s fine{ELL} ok -- yes.</p>"
    for exact in (
        'said "hello - world"; it\'s fine... ok - yes.',
        f"said {LDQ}hello {EN} world{RDQ}; it{RSQ}s fine... ok --- yes.",
    ):
        assert tokens_of(html, exact=exact) == [1]
    plain = '<p>a "b" c - d... e</p>'
    assert tokens_of(plain, exact=f"{LDQ}b{RDQ} c {EM} d{ELL} e") == [1]


def test_typography_marks_the_whole_original_text(path: str) -> None:
    add(path, anchor={"exact": "it's fine - really"})
    _, out = run(path, f"<p>Say it{RSQ}s fine -- really.</p>")
    assert f">it{RSQ}s fine -- really</mark>" in out


def test_word_boundary_hit_beats_mid_word_hit() -> None:
    html = "<p>concatenate</p><p>a cat sat</p>"
    assert tokens_of(html, exact="cat") == [4]
    assert tokens_of(html, exact="cat", suffix="enate") == [4]
    assert tokens_of("<p>concat</p>", exact="cat") == [1]


def test_unclosed_head_ends_at_body_or_first_content_tag() -> None:
    for html in (
        "<html><head><title>t</title><body><p>seen words</p>",
        "<html><head><meta charset=x><p>seen words</p>",
    ):
        assert embed.locate(embed._parse(html), {"exact": "seen words"}, {}) is not None
    hidden = "<html><head><title>seen words</title><style></style></head><body></body>"
    assert embed.locate(embed._parse(hidden), {"exact": "seen words"}, {}) is None


def test_text_in_form_and_embedded_elements_is_not_matched() -> None:
    for tag in ("textarea", "title", "svg", "math", "template", "noscript", "select"):
        html = f"<body><{tag}>hidden words</{tag}><p>shown words</p>"
        doc = embed._parse(html)
        assert embed.locate(doc, {"exact": "hidden words"}, {}) is None, tag
        assert embed.locate(doc, {"exact": "shown words"}, {}) is not None, tag
    doc = embed._parse("<select><option>one words<option>two words</select><p>after words</p>")
    assert embed.locate(doc, {"exact": "two words"}, {}) is None
    assert embed.locate(doc, {"exact": "after words"}, {}) is not None


def test_ref_goes_after_the_link_that_holds_the_anchor(path: str) -> None:
    add(path, anchor={"exact": "linked words"})
    _, html = run(path, '<p>See <a href="/x"><em>some linked words</em></a> here.</p>')
    assert "</mark></em></a><sup" in html and html.count("<sup") == 1


def test_stepping_counts_claims_not_marks(path: str) -> None:
    add(path, anchor={"exact": "cut unchecked  citations in trials"})
    _, html = run(path, layout="panel")
    assert html.count('data-claim="C-0001"') == 2
    script = html.split("<script>")[1]
    assert 'title.textContent = id + " (passage "' in script and "firsts.length" in script
    assert "firsts.indexOf(current)" in script


def test_unlocated_anchor_text_stays_out_at_masked_and_locator_levels(path: str) -> None:
    add(path, anchor={"exact": "words absent zzz", "prefix": "before qqq", "suffix": "after www"})
    for level in ("masked", "locator"):
        _, html = run_new(path, level=level)
        assert "absent zzz" not in html and "qqq" not in html and "www" not in html
        assert "Text not found in the work." in html
    _, full = run_new(path, level="full")
    assert "absent zzz" in full and "before qqq" in full


def test_other_anchors_of_a_located_claim_are_shown(path: str) -> None:
    add(path, claim_id="C-0001")
    add(path, claim_id="C-0001", key="otherStudy", anchor={"exact": "second spot xyz"})
    add(path, claim_id="C-0001", key="thirdStudy")
    _, full = run(path, level="full")
    assert full.count("second spot xyz") == 1 and full.count("In the work") == 1
    _, masked = run_new(path, level="masked")
    assert "second spot xyz" not in masked
    assert "Anchor text withheld at this level." in masked


def test_charset_is_utf8_and_added_text_is_ascii(path: str) -> None:
    add(path)
    for layout in embed.LAYOUTS:
        _, html = run_new(path, layout=layout)
        assert html.isascii()
    latin = HTML.replace("<head>", '<head><meta charset="ISO-8859-1">', 1)
    _, html = run_new(path, latin)
    assert 'charset="utf-8"' in html and "ISO-8859-1" not in html
    http = HTML.replace(
        "<head>", '<head><meta http-equiv="Content-Type" content="text/html; charset=windows-1252">'
    )
    _, html = run_new(path, http)
    assert "charset=utf-8" in html and "1252" not in html and html.count("charset") == 1
    _, html = run_new(path)
    assert html.count("charset") == 1
    assert html.startswith('<!DOCTYPE html><html><head><meta charset="utf-8">')


def test_insertion_points_ignore_tags_inside_scripts_and_comments(path: str) -> None:
    add(path)
    script = '<script>const t = "<head></head><body></body><meta charset=latin1>";</script>'
    work = (
        f"<!DOCTYPE html><html><head>{script}<!-- </head> --></head>"
        f"<body>{script}<p>Plain: cut unchecked citations.</p></body></html>"
    )
    _, html = run(path, work, layout="panel")
    assert html.count(script) == 2
    assert html.index("<style>") > html.index("<!-- </head> -->")
    assert html.index('class="el-hint"') > html.index("<body>")


def test_hint_follows_the_head_when_the_body_tag_is_omitted(path: str) -> None:
    add(path)
    work = (
        "<!DOCTYPE html><html><head><title>W</title></head>"
        "<p>Plain: cut unchecked citations.</p></html>"
    )
    _, html = run(path, work, layout="panel")
    assert html.startswith("<!DOCTYPE html>")
    assert html.index('class="el-hint"') > html.index("</head>")


def test_refuses_a_work_with_a_base_url(path: str) -> None:
    add(path)
    folder = Path(path).parent
    work = folder / "work.html"
    work.write_text('<head><base href="https://example.org/"></head><p>x</p>', "utf-8")
    with pytest.raises(ValueError, match="base"):
        embed.embed_ledger(path, str(work), str(folder / "embedded.html"))
    assert not (folder / "embedded.html").exists()
