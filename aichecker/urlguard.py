"""Turn user text into a safe http(s) URL, and keep the browser off private networks.

The bot opens arbitrary links, so without this a user could make it screenshot
http://localhost:8080/admin or the cloud metadata endpoint (SSRF). Every request
the browser makes — redirects and subresources included — is checked by
``check_host`` (see ``capture.install_guard``). DNS rebinding is not fully
covered because Chromium resolves names itself; run the bot on a host without
sensitive internal services if that matters to you.
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from urllib.parse import urlsplit, urlunsplit

_TRAILING = ".,;:!?)]}>»\"'…"
_LEADING = "<«\"'(["
_SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa", ".intranet")


class UrlError(ValueError):
    """``code`` is one of: invalid, scheme, private, unresolvable."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def _looks_like_domain(token: str) -> bool:
    host = re.split(r"[/?#]", token, maxsplit=1)[0].rsplit(":", 1)[0]
    if not host or "@" in host:
        return False
    labels = host.split(".")
    if len(labels) < 2 or not all(labels):
        return False
    tld = labels[-1]
    return (tld.isalpha() and len(tld) >= 2) or tld.lower().startswith("xn--")


def extract_url(text: str) -> str | None:
    """The first token in ``text`` that looks like a web address, or None."""
    for token in text.split():
        token = token.lstrip(_LEADING).rstrip(_TRAILING)
        if token and (re.match(r"^https?://", token, re.I) or _looks_like_domain(token)):
            return token
    return None


def normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw:
        raise UrlError("invalid")
    if not _SCHEME.match(raw):
        # "javascript:…", "data:…", "mailto:…" — but "localhost:3000" is a host with a port.
        if re.match(r"^[a-z][a-z0-9+.-]*:(?!\d)", raw, re.I):
            raise UrlError("scheme", raw.split(":", 1)[0])
        raw = "https://" + raw
    try:
        parts = urlsplit(raw)
        port = parts.port
    except ValueError as exc:
        raise UrlError("invalid", str(exc)) from exc
    if parts.scheme.lower() not in ("http", "https"):
        raise UrlError("scheme", parts.scheme)
    if not parts.hostname or parts.username or parts.password:
        raise UrlError("invalid")
    host = parts.hostname.rstrip(".")
    try:
        host.encode("idna")
    except UnicodeError as exc:
        raise UrlError("invalid", str(exc)) from exc
    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def _is_public_ip(value: str) -> bool:
    addr = ipaddress.ip_address(value.split("%", 1)[0])
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return addr.is_global and not addr.is_multicast


async def check_host(host: str | None) -> str:
    """'ok' for public hosts, otherwise 'private' or 'unresolvable'."""
    host = (host or "").strip("[]").rstrip(".").lower()
    if not host:
        return "unresolvable"
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        return "private"
    try:
        return "ok" if _is_public_ip(host) else "private"
    except ValueError:
        pass  # not an IP literal
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        return "unresolvable"
    addresses = {info[4][0] for info in infos}
    if not addresses:
        return "unresolvable"
    return "ok" if all(_is_public_ip(a) for a in addresses) else "private"


async def validate_url(raw: str, allow_private: bool = False) -> str:
    url = normalize_url(raw)
    if not allow_private:
        verdict = await check_host(urlsplit(url).hostname)
        if verdict != "ok":
            raise UrlError(verdict, url)
    return url
