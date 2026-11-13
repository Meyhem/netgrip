"""Domain matching for the source filters (W4)."""

from urllib.parse import urlsplit


def host_excluded(url: str, domains: list[str]) -> bool:
    """Whether the URL's host is one of `domains` or a subdomain of one."""
    host = (urlsplit(url).hostname or "").lower()
    bare = [d.lower().strip().lstrip(".") for d in domains if d.strip()]
    return any(host == d or host.endswith("." + d) for d in bare)
