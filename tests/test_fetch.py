from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

from evidence_ledger_mcp import checks, fetch, ledger

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
PROVENANCE = {"by_type": "agent", "by": "Claude Code", "model": "claude-opus-5-5"}
HTML = (
    "<html><head><title>T</title><script>var x = 1;</script></head>"
    f"<body><p>{QUOTE}.</p></body></html>"
)
PUBLIC = "93.184.216.34"
LOCAL = ["127.0.0.1"]


def page(
    body: str | bytes = HTML,
    content_type: str = "text/html",
    status: int = 200,
    location: str | None = None,
    charset: str | None = "utf-8",
) -> fetch.Response:
    data = body.encode("utf-8") if isinstance(body, str) else body
    return fetch.Response(status, content_type, charset, location, data)


class Net:
    """Offline DNS and HTTP: `hosts` maps names to addresses, `pages` urls to replies."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, pages: dict[str, fetch.Response]) -> None:
        self.hosts: dict[str, list[str]] = {}
        self.pages = pages
        monkeypatch.setattr(fetch, "_resolve", lambda host, port: self.hosts.get(host, [PUBLIC]))
        monkeypatch.setattr(fetch, "_open", self.open)

    def open(
        self, url: str, addresses: list[str], timeout: float, max_bytes: int
    ) -> fetch.Response:
        if url not in self.pages:
            raise fetch.FetchError("HTTP 404")
        return self.pages[url]


@pytest.fixture
def path(tmp_path: Path) -> str:
    target = str(tmp_path / "ledger.jsonl")
    ledger.create_ledger(target, {"title": "Example work", "type": "manuscript"})
    ledger.add_record(target, RECORD, PROVENANCE)
    return target


def quotes(path: str, url: str) -> dict[str, Any]:
    result = checks.check_ledger(path, source_urls={"exampleStudy2026": url})
    quotes: dict[str, Any] = result["quotes"]
    return quotes


def test_html_text_is_matched(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    Net(monkeypatch, {"https://a.org/p": page()})
    assert quotes(path, "https://a.org/p") == {
        "matched": ["R-0001"],
        "not_found": [],
        "no_source": [],
        "fetch_failed": {},
    }


def test_html_markup_and_scripts_are_not_text() -> None:
    text = fetch._text(page())
    assert "var x" not in text
    assert "<p>" not in text


def test_plain_text_and_charset(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    other = page("A different passage, café.".encode("latin-1"), "text/plain", charset="latin-1")
    Net(monkeypatch, {"http://a.org/t": other})
    assert quotes(path, "http://a.org/t")["not_found"] == ["R-0001"]
    assert "café" in fetch._text(other)
    assert fetch._text(page(QUOTE, "text/plain", charset="no-such-charset")) == QUOTE


def test_text_is_never_in_the_result(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    Net(monkeypatch, {"https://a.org/p": page()})
    result = checks.check_ledger(path, source_urls={"exampleStudy2026": "https://a.org/p"})
    dumped = json.dumps(result)
    assert "unchecked" not in dumped
    assert "var x" not in dumped


@pytest.mark.parametrize(
    "address", ["127.0.0.1", "10.0.0.5", "169.254.169.254", "::1", "fe80::1%2"]
)
def test_non_public_address_is_refused(
    path: str, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    net = Net(monkeypatch, {"https://a.org/p": page()})
    net.hosts["a.org"] = [PUBLIC, address]
    result = quotes(path, "https://a.org/p")
    assert result["fetch_failed"] == {"exampleStudy2026": "non-public address"}
    assert result["no_source"] == ["R-0001"]


def test_redirect_to_non_public_address_is_refused(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    net = Net(monkeypatch, {"https://a.org/p": page(status=302, location="http://inner.test/x")})
    net.pages["http://inner.test/x"] = page()
    net.hosts["inner.test"] = ["192.168.1.1"]
    assert quotes(path, "https://a.org/p")["fetch_failed"] == {
        "exampleStudy2026": "non-public address"
    }


def test_redirects_are_followed_and_capped(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    Net(
        monkeypatch,
        {
            "https://a.org/p": page(status=301, location="/q"),
            "https://a.org/q": page(),
            "https://a.org/loop": page(status=302, location="/loop"),
        },
    )
    assert quotes(path, "https://a.org/p")["matched"] == ["R-0001"]
    assert quotes(path, "https://a.org/loop")["fetch_failed"] == {
        "exampleStudy2026": "too many redirects"
    }


@pytest.mark.parametrize("url", ["ftp://a.org/p", "file:///etc/passwd", "a.org/p", "http:///p"])
def test_bad_scheme_is_refused(path: str, monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    Net(monkeypatch, {})
    assert quotes(path, url)["fetch_failed"] == {"exampleStudy2026": "not http(s)"}


def test_unsupported_type_and_http_error(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    Net(monkeypatch, {"https://a.org/f.pdf": page("%PDF", "application/pdf")})
    assert quotes(path, "https://a.org/f.pdf")["fetch_failed"] == {
        "exampleStudy2026": "unsupported content type application/pdf"
    }
    assert quotes(path, "https://a.org/missing")["fetch_failed"] == {"exampleStudy2026": "HTTP 404"}


def test_key_in_both_sources_and_source_urls_is_an_error(path: str) -> None:
    with pytest.raises(ValueError, match="exampleStudy2026"):
        checks.check_ledger(
            path,
            sources={"exampleStudy2026": "a"},
            source_urls={"exampleStudy2026": "http://a.org"},
        )


def test_fetched_and_supplied_sources_combine(path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger.add_record(path, {**RECORD, "key": "other2026"}, PROVENANCE)
    Net(monkeypatch, {"https://a.org/p": page()})
    result = checks.check_ledger(
        path, sources={"other2026": "nothing"}, source_urls={"exampleStudy2026": "https://a.org/p"}
    )
    assert result["quotes"]["matched"] == ["R-0001"]
    assert result["quotes"]["not_found"] == ["R-0002"]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        route = self.path
        if route == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif route == "/missing":
            self.send_error(404, "secret page text")
        elif route == "/garbage":
            self.wfile.write(b"garbage\r\n\r\n")
        elif route == "/big":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"x" * 5000)
        elif route == "/notype":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"hello")
        elif route == "/drip":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            try:
                for _ in range(40):
                    self.wfile.write(b"x")
                    self.wfile.flush()
                    time.sleep(0.05)
            except OSError:
                pass
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"hello")


@pytest.fixture
def base() -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_open_returns_redirects_and_plain_pages(base: str) -> None:
    redirect = fetch._open(f"{base}/redirect", LOCAL, 5, 1000)
    assert (redirect.status, redirect.location) == (302, "/ok")
    page_ = fetch._open(f"{base}/ok", LOCAL, 5, 1000)
    assert (page_.content_type, page_.body) == ("text/plain", b"hello")


def test_open_failures_become_short_reasons(base: str) -> None:
    for route, reason in [
        ("/missing", "HTTP 404"),
        ("/garbage", "network error"),
        ("/big", "too large"),
    ]:
        with pytest.raises(fetch.FetchError) as caught:
            fetch._open(base + route, LOCAL, 5, 1000)
        assert str(caught.value) == reason
    with pytest.raises(fetch.FetchError, match="bad url"):
        fetch._open("http://[::1", LOCAL, 5, 1000)
    with pytest.raises(fetch.FetchError, match="bad url"):
        fetch._open(f"{base}/a b", LOCAL, 5, 1000)
    with pytest.raises(fetch.FetchError, match="network error"):
        fetch._open("http://127.0.0.1:1/", LOCAL, 5, 1000)


def test_open_enforces_a_total_deadline(base: str) -> None:
    started = time.monotonic()
    with pytest.raises(fetch.FetchError, match="timeout"):
        fetch._open(f"{base}/drip", LOCAL, 0.3, 1000)
    assert time.monotonic() - started < 1.5


def test_missing_content_type_is_unsupported(base: str) -> None:
    reply = fetch._open(f"{base}/notype", LOCAL, 5, 1000)
    assert reply.content_type == ""
    with pytest.raises(fetch.FetchError) as caught:
        fetch._text(reply)
    assert str(caught.value) == "unsupported content type"


def test_odd_content_type_is_not_echoed() -> None:
    with pytest.raises(fetch.FetchError) as caught:
        fetch._text(page("x", "x/<script>alert(1)"))
    assert str(caught.value) == "unsupported content type"


@pytest.mark.parametrize(
    "address", ["0.0.0.0", "::ffff:127.0.0.1", "64:ff9b::a00:1", "64:ff9b::7f00:1"]
)
def test_more_non_public_addresses(
    path: str, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    net = Net(monkeypatch, {"https://a.org/p": page()})
    net.hosts["a.org"] = [address]
    assert quotes(path, "https://a.org/p")["fetch_failed"] == {
        "exampleStudy2026": "non-public address"
    }


def test_nat64_with_public_embedded_address_is_allowed() -> None:
    assert fetch._is_global("64:ff9b::5db8:d822")


def test_redirect_without_location_or_to_a_file_fails(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    Net(
        monkeypatch,
        {
            "https://a.org/none": page(status=302),
            "https://a.org/file": page(status=302, location="file:///etc/passwd"),
        },
    )
    assert quotes(path, "https://a.org/none")["fetch_failed"] == {
        "exampleStudy2026": "network error"
    }
    assert quotes(path, "https://a.org/file")["fetch_failed"] == {"exampleStudy2026": "not http(s)"}


def test_five_redirects_are_followed_but_six_fail(
    path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    pages = {f"https://a.org/{n}": page(status=302, location=f"/{n + 1}") for n in range(6)}
    pages["https://a.org/5"] = page()
    pages["https://a.org/6"] = page()
    Net(monkeypatch, pages)
    assert quotes(path, "https://a.org/0")["matched"] == ["R-0001"]
    pages["https://a.org/5"] = page(status=302, location="/6")
    assert quotes(path, "https://a.org/0")["fetch_failed"] == {
        "exampleStudy2026": "too many redirects"
    }


@pytest.mark.parametrize("url", ["http://[::1", "http://user:pw@192.0.2.1/", "http://a.org:99999/"])
def test_bad_urls_are_reported_not_raised(
    path: str, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    Net(monkeypatch, {})
    assert quotes(path, url)["fetch_failed"] == {"exampleStudy2026": "bad url"}


@pytest.mark.network
def test_real_page_is_fetched(path: str) -> None:
    text = fetch.fetch_text("https://example.com")
    assert "documentation examples" in text


def test_connection_is_pinned_to_the_checked_address(
    base: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = socket.getaddrinfo

    def no_names(host: str, *args: Any, **kwargs: Any) -> Any:
        assert host == "127.0.0.1", "resolved the hostname again"
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", no_names)
    port = base.rsplit(":", 1)[1]
    reply = fetch._open(f"http://pinned.test:{port}/ok", LOCAL, 5, 1000)
    assert reply.body == b"hello"


def test_header_drip_hits_the_total_deadline() -> None:
    server = socket.create_server(("127.0.0.1", 0))

    def drip() -> None:
        conn, _ = server.accept()
        try:
            conn.recv(4096)
            for byte in b"HTTP/1.1 200 OK\r\nX-A: " + b"a" * 100:
                conn.sendall(bytes([byte]))
                time.sleep(0.05)
        except OSError:
            pass
        finally:
            conn.close()

    threading.Thread(target=drip, daemon=True).start()
    started = time.monotonic()
    try:
        with pytest.raises(fetch.FetchError, match="timeout"):
            fetch._open(f"http://127.0.0.1:{server.getsockname()[1]}/", LOCAL, 0.3, 1000)
    finally:
        server.close()
    assert time.monotonic() - started < 1.5


def test_unusable_charset_falls_back_to_utf8() -> None:
    assert fetch._text(page(QUOTE, "text/plain", charset="idna")) == QUOTE
