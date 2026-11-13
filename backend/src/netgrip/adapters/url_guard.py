"""Which URLs the fetcher may request: http(s) to public addresses only (P7, tech spec 9)."""

import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


def _bad_address(ip: ipaddress._BaseAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_unspecified
        or ip.is_multicast
        or ip.is_reserved
    )


def check_url(url: str) -> str | None:
    """None when the URL may be fetched, else the reason it may not."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
        parts.port  # noqa: B018 - raises ValueError for a bad port
    except ValueError:
        return "not a valid URL"
    if parts.scheme not in ("http", "https"):
        return f"scheme {parts.scheme or '(none)'!r} is not http or https"
    if not host:
        return "no host"
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        return f"{host} is not a public address" if _bad_address(literal) else None
    if host.lower() == "localhost" or host.lower().endswith(".localhost"):
        return "localhost is not a public address"
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except OSError:
        return None  # unresolvable: the request itself will fail and be recorded
    for info in infos:
        if _bad_address(ipaddress.ip_address(info[4][0].split("%")[0])):
            return f"{host} resolves to a non-public address"
    return None


async def acheck_url(url: str) -> str | None:
    return await asyncio.to_thread(check_url, url)
