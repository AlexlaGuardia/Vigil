"""SSRF guard for outbound requests to user-configured URLs.

A webhook trigger's `action_config` supplies the destination URL. Without a
check, a caller can point it at addresses the server can reach but they cannot:
cloud metadata (169.254.169.254), loopback, or RFC1918 internal services. Before
any such request, resolve the host and refuse every non-public destination.

Best-effort by design: this resolves the host now and validates each address. A
hostname that later rebinds to a private IP (DNS rebinding) is out of scope for
this stored-config threat model — but literal internal targets, and hostnames
that currently resolve to internal addresses, are refused.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_ALLOWED_SCHEMES = {"http", "https"}


class UnsafeURLError(ValueError):
    """The URL targets a non-public / internal address and must not be fetched."""


def _ip_is_public(ip: str) -> bool:
    addr = ipaddress.ip_address(ip.split("%")[0])  # drop any IPv6 scope id
    # An IPv4-mapped IPv6 address (::ffff:127.0.0.1) must be judged on its v4 form.
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or addr.is_unspecified
    )


def assert_public_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is http(s) and every resolved IP is public."""
    if not url or not isinstance(url, str):
        raise UnsafeURLError("empty url")

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise UnsafeURLError(f"scheme {parsed.scheme!r} not allowed (http/https only)")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("url has no host")

    port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"cannot resolve host {host!r}: {exc}")

    ips = {info[4][0] for info in infos}
    if not ips:
        raise UnsafeURLError(f"host {host!r} did not resolve")

    for ip in ips:
        if not _ip_is_public(ip):
            raise UnsafeURLError(
                f"host {host!r} resolves to non-public address {ip}"
            )
