"""Conservative, public-Internet-only URL validation (default-deny)."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

TRACKING = frozenset({"fbclid", "gclid", "msclkid", "yclid"})
MAX_URL_LENGTH = 2048


class UnsafeURL(ValueError):
    """Rejected URL: invalid host, non-public address, or disallowed scheme."""


def normalize_url(raw: str, base: str | None = None) -> str:
    raw = (raw or "").strip()
    if base:
        raw = urljoin(base, raw)
    if len(raw) > MAX_URL_LENGTH or not raw or any(ord(c) < 32 for c in raw):
        raise UnsafeURL("URL is empty, too long, or contains control characters")
    try:
        parsed = urlsplit(raw)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise UnsafeURL("Invalid authority/port") from exc
    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https") or not host:
        raise UnsafeURL("Only HTTP(S) URLs with a hostname are supported")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeURL("Userinfo in URLs is forbidden")
    try:
        host = host.encode("idna").decode("ascii").lower().rstrip(".")
    except (UnicodeError, ValueError) as exc:
        raise UnsafeURL("Invalid IDN") from exc
    if not host or "_" in host or ".." in host:
        raise UnsafeURL("Malformed hostname")
    if port is not None and (port <= 0 or port > 65535):
        raise UnsafeURL("Invalid port")
    if port in (80 if scheme == "http" else 443, None):
        netloc = host
    else:
        netloc = f"{host}:{port}"
    # IPv6 literals: use brackets when constructing the URL.
    if ":" in host:
        netloc = f"[{host}]" + (f":{port}" if port is not None and port != (80 if scheme == "http" else 443) else "")
    pairs = parse_qsl(parsed.query, keep_blank_values=True, max_num_fields=100)
    pairs = [(k, v) for k, v in pairs if not k.lower().startswith("utm_") and k.lower() not in TRACKING]
    return urlunsplit((scheme, netloc, parsed.path or "/", urlencode(pairs, doseq=True), ""))


def url_host(url: str) -> str:
    return urlsplit(normalize_url(url)).hostname or ""


def assert_public_url(url: str, allowed_host: str | None = None, resolve: bool = True) -> str:
    """Validate before *each* fetch, including after DNS changes.

    In V1 redirects are disabled, avoiding implicit hops outside the allowlisted
    host. This does not offer a kernel-level protection against DNS rebinding
    between validation and TCP connection; isolate workers at the network layer
    when crawling untrusted destinations.
    """
    normalized = normalize_url(url)
    parsed = urlsplit(normalized)
    hostname = parsed.hostname or ""
    if allowed_host and hostname != allowed_host.lower():
        raise UnsafeURL("Outbound host is outside this seed domain")
    if hostname in ("localhost", "localhost.localdomain") or hostname.endswith(".localhost"):
        raise UnsafeURL("Loopback hostname is forbidden")
    if hostname.endswith((".local", ".internal", ".test", ".invalid")):
        raise UnsafeURL("Non-public DNS suffix is forbidden")
    try:
        literal = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise UnsafeURL("Non-global IP address is forbidden")
    if resolve:
        try:
            infos = socket.getaddrinfo(hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                                       type=socket.SOCK_STREAM)
        except (OSError, UnicodeError) as exc:
            raise UnsafeURL("DNS lookup failed") from exc
        if not infos or any(not ipaddress.ip_address(entry[4][0]).is_global for entry in infos):
            raise UnsafeURL("DNS must resolve exclusively to public IP addresses")
    return normalized
