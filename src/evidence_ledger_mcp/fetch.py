"""Fetch the text of a public web page for the quote re-check; failures give short fixed reasons."""

from __future__ import annotations

import http.client
import ipaddress
import re
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

from evidence_ledger_mcp import embed

TIMEOUT = 15  # seconds in total for one fetch, redirects included (DNS lookups excepted)
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
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


def _open(url: str, timeout: float, max_bytes: int) -> Response:
    """One request without following redirects, within `timeout` seconds in total; tests replace
    this to stay offline."""
    deadline = time.monotonic() + timeout
    # No proxy: the address check above is on this machine's DNS, which a proxy would bypass.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect)
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "evidence-ledger-mcp"})
        with opener.open(request, timeout=timeout) as reply:
            return _response(reply, max_bytes, deadline)
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


def _check_public(url: str) -> None:
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
    # The connection resolves the host again, so a rebinding DNS server could still slip through.
    if not public:
        raise FetchError("non-public address")


def _text(response: Response) -> str:
    if response.content_type not in TEXT_TYPES:
        named = TYPE_NAME.match(response.content_type)
        raise FetchError(f"unsupported content type{f' {response.content_type}' if named else ''}")
    try:
        text = response.body.decode(response.charset or "utf-8", "replace")
    except LookupError:
        text = response.body.decode("utf-8", "replace")
    return embed._parse(text).text if response.content_type in HTML_TYPES else text


def fetch_text(url: str) -> str:
    """The visible text of an http(s) page; raises FetchError with a short reason."""
    deadline = time.monotonic() + TIMEOUT
    for _ in range(MAX_REDIRECTS + 1):
        _check_public(url)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FetchError("timeout")
        response = _open(url, remaining, MAX_BYTES)
        if response.status not in REDIRECTS:
            return _text(response)
        if not response.location:
            raise FetchError("network error")
        url = urljoin(url, response.location)
    raise FetchError("too many redirects")
