"""Fetch the text of a public web page for the quote re-check; failures give short fixed reasons."""

from __future__ import annotations

import contextlib
import functools
import http.client
import io
import ipaddress
import json
import logging
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

import pypdf

from evidence_ledger_mcp import embed

TIMEOUT = 15  # seconds in total for one fetch, redirects included (DNS lookups excepted)
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_PAGES = 2000
MAX_CHARS = 20 * 1024 * 1024  # of extracted PDF text
PDF_TIMEOUT = 15  # seconds for PDF text extraction, which runs in a child process
PDF_TYPES = ("application/pdf", "application/x-pdf")
OCTET_TYPES = ("application/octet-stream", "binary/octet-stream")
CHUNK = 64 * 1024
HTML_TYPES = ("text/html", "application/xhtml+xml")
TEXT_TYPES = (*HTML_TYPES, "text/plain")
REDIRECTS = (301, 302, 303, 307, 308)
NAT64 = ipaddress.ip_network("64:ff9b::/96")
TYPE_NAME = re.compile(r"^[a-z0-9.+-]{1,40}/[a-z0-9.+-]{1,60}$")


class FetchError(Exception):
    """A fetch that failed; the message is a short fixed reason, never page content."""


@dataclass
class Response:
    status: int
    content_type: str
    charset: str | None
    location: str | None
    body: bytes


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # redirects are followed by `fetch_text`, which checks every hop


def _resolve(host: str, port: int) -> list[str]:
    """Addresses of a host; tests replace this to stay offline."""
    return [str(info[4][0]) for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]


class _Pin:
    """Connects only to the addresses already checked, and closes the socket at the deadline."""

    def __init__(self, addresses: list[str], deadline: float) -> None:
        self.addresses = addresses
        self.deadline = deadline
        self.sock: socket.socket | None = None
        self.expired = False

    def connect(self, port: int) -> socket.socket:
        error: OSError = OSError("no address")
        for address in self.addresses:
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                self.sock = socket.create_connection((address, port), timeout=remaining)
            except OSError as exc:
                error = exc
                continue
            if self.expired:
                self.sock.close()
                raise TimeoutError
            return self.sock
        raise error

    def expire(self) -> None:
        self.expired = True
        if (sock := self.sock) is not None:
            with contextlib.suppress(OSError):
                sock.shutdown(socket.SHUT_RDWR)  # wakes a read blocked in another thread
            sock.close()


class _Http(http.client.HTTPConnection):
    def __init__(self, *args: Any, pin: _Pin, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pin = pin

    def connect(self) -> None:
        self.sock = self.pin.connect(self.port)


class _Https(http.client.HTTPSConnection):
    def __init__(self, *args: Any, pin: _Pin, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.pin = pin

    def connect(self) -> None:
        sock = self.pin.connect(self.port)
        context = ssl.create_default_context()
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        # Certificate and SNI are checked against the hostname, not the pinned address.
        self.sock = context.wrap_socket(sock, server_hostname=self.host)


class _HttpHandler(urllib.request.HTTPHandler):
    def __init__(self, pin: _Pin) -> None:
        super().__init__()
        self.pin = pin

    def http_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_Http, pin=self.pin), req)


class _HttpsHandler(urllib.request.HTTPSHandler):
    def __init__(self, pin: _Pin) -> None:
        super().__init__()
        self.pin = pin

    def https_open(self, req: urllib.request.Request) -> http.client.HTTPResponse:
        return self.do_open(functools.partial(_Https, pin=self.pin), req)


def _open(url: str, addresses: list[str], timeout: float, max_bytes: int) -> Response:
    """One request without following redirects, connecting only to `addresses` and finishing
    within `timeout` seconds in total; tests replace this to stay offline."""
    pin = _Pin(addresses, time.monotonic() + timeout)
    watchdog = threading.Timer(timeout, pin.expire)
    watchdog.daemon = True
    watchdog.start()
    try:
        response = _send(url, pin, timeout, max_bytes)
    except FetchError as exc:
        if pin.expired:
            raise FetchError("timeout") from exc
        raise
    finally:
        watchdog.cancel()
    if pin.expired:  # a socket closed at the deadline can read as a clean end of the body
        raise FetchError("timeout")
    return response


def _send(url: str, pin: _Pin, timeout: float, max_bytes: int) -> Response:
    # No proxy: the address check is on this machine's DNS, which a proxy would bypass.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), _NoRedirect, _HttpHandler(pin), _HttpsHandler(pin)
    )
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "evidence-ledger-mcp"})
        with opener.open(request, timeout=timeout) as reply:
            return _response(reply, max_bytes, pin.deadline)
    except urllib.error.HTTPError as exc:
        if exc.code in REDIRECTS:
            return Response(exc.code, "", None, exc.headers.get("Location"), b"")
        raise FetchError(f"HTTP {exc.code}") from exc
    except FetchError:
        raise
    except TimeoutError as exc:
        raise FetchError("timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ValueError | UnicodeError):
            raise FetchError("bad url") from exc
        raise FetchError(
            "timeout" if isinstance(exc.reason, TimeoutError) else "network error"
        ) from exc
    except (ValueError, UnicodeError, http.client.InvalidURL) as exc:
        raise FetchError("bad url") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise FetchError("network error") from exc


def _response(reply: Any, max_bytes: int, deadline: float) -> Response:
    headers = reply.headers
    chunks: list[bytes] = []
    size = 0
    while chunk := reply.read1(min(CHUNK, max_bytes + 1 - size)):
        chunks.append(chunk)
        size += len(chunk)
        if size > max_bytes:
            raise FetchError("too large")
        if time.monotonic() > deadline:
            raise FetchError("timeout")
    length = headers.get("Content-Length")
    if length and length.isdigit() and size < int(length):
        raise FetchError("incomplete response")
    content_type = headers.get_content_type() if headers.get("Content-Type") else ""
    return Response(
        reply.status, content_type, headers.get_content_charset(), None, b"".join(chunks)
    )


def _is_global(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return ip.ipv4_mapped.is_global
        if ip in NAT64 and not ipaddress.IPv4Address(ip.packed[-4:]).is_global:
            return False
    return ip.is_global


def _check_public(url: str) -> list[str]:
    """The resolved addresses of the URL's host, all public; the connection is pinned to them."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise FetchError("not http(s)")
        if "@" in parts.netloc:
            raise FetchError("bad url")
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("bad url") from exc
    try:
        addresses = _resolve(parts.hostname, port)
        public = bool(addresses) and all(_is_global(a) for a in addresses)
    except (OSError, ValueError) as exc:
        raise FetchError("network error") from exc
    if not public:
        raise FetchError("non-public address")
    return addresses


@dataclass
class Pdf:
    pages: list[str]  # the text of each page; hyphenation across lines is left as is
    labels: list[str]  # the printed page numbers, e.g. "347" or "xiv"; empty if the PDF has none


def _pdf_pages(body: bytes, max_pages: int) -> Pdf:
    """The text and page labels of a PDF."""
    try:
        reader = pypdf.PdfReader(io.BytesIO(body))
        if reader.is_encrypted and reader.decrypt("") == pypdf.PasswordType.NOT_DECRYPTED:
            raise FetchError("encrypted pdf")
        if len(reader.pages) > max_pages:
            raise FetchError("pdf too long")
        texts: list[str] = []
        size = 0
        for page in reader.pages:
            texts.append(page.extract_text())
            size += len(texts[-1])
            if size > MAX_CHARS:
                raise FetchError("pdf too long")
        labels = list(reader.page_labels) if "/PageLabels" in reader.root_object else []
    except FetchError:
        raise
    except Exception as exc:  # malformed PDFs raise PyPdfError, ValueError, KeyError, ...
        raise FetchError("unreadable pdf") from exc
    if not any(text.strip() for text in texts):
        raise FetchError("no text in pdf")
    return Pdf(texts, labels)


def _pdf_worker() -> None:
    """Read a PDF from stdin and write `[ok, pages and labels or reason]` as JSON to stdout."""
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # its warnings can quote the file
    try:
        pdf = _pdf_pages(sys.stdin.buffer.read(), int(sys.argv[1]))
        result: list[Any] = [True, [pdf.pages, pdf.labels]]
    except FetchError as exc:
        result = [False, str(exc)]
    sys.stdout.write(json.dumps(result))


def pdf_pages(body: bytes) -> Pdf:
    """`_pdf_pages` in a child process that is killed after PDF_TIMEOUT, since a single
    page's extraction cannot be interrupted and hostile PDFs can take hours. The child gets
    pipes of its own: on Windows, a child inheriting the MCP server's stdin, which the server
    is blocked reading, hangs at startup."""
    try:
        run = subprocess.run(
            [sys.executable, "-I", "-m", "evidence_ledger_mcp.fetch", str(MAX_PAGES)],
            input=body,
            capture_output=True,
            timeout=PDF_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise FetchError("pdf too slow") from exc
    try:
        ok, value = json.loads(run.stdout)
    except ValueError as exc:  # the child died, e.g. out of memory
        raise FetchError("unreadable pdf") from exc
    if not ok:
        raise FetchError(str(value))
    return Pdf(*value)


def _text(response: Response) -> str:
    is_pdf = response.content_type in OCTET_TYPES and b"%PDF-" in response.body[:1024]
    if response.content_type in PDF_TYPES or is_pdf:
        return "\n".join(pdf_pages(response.body).pages)
    if response.content_type not in TEXT_TYPES:
        named = TYPE_NAME.match(response.content_type)
        raise FetchError(f"unsupported content type{f' {response.content_type}' if named else ''}")
    try:
        text = response.body.decode(response.charset or "utf-8", "replace")
    except (LookupError, UnicodeError, ValueError):
        text = response.body.decode("utf-8", "replace")
    return embed._parse(text).text if response.content_type in HTML_TYPES else text


def fetch_text(url: str) -> str:
    """The visible text of an http(s) page; raises FetchError with a short reason."""
    deadline = time.monotonic() + TIMEOUT
    for _ in range(MAX_REDIRECTS + 1):
        addresses = _check_public(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("timeout")
        response = _open(url, addresses, remaining, MAX_BYTES)
        if response.status not in REDIRECTS:
            return _text(response)
        if not response.location:
            raise FetchError("network error")
        url = urljoin(url, response.location)
    raise FetchError("too many redirects")


if __name__ == "__main__":  # the PDF worker, run by `pdf_pages`
    _pdf_worker()
