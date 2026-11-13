"""The simple fetch route: plain HTTP, no browser (W2)."""

import asyncio
from collections.abc import Callable
from urllib.parse import urljoin, urlsplit

import httpx

from netgrip.adapters.extractor import extract
from netgrip.adapters.fetch_limits import DEFAULT_LIMITS, USER_AGENT, FetchLimits
from netgrip.adapters.fetcher import FetchAttempt, PageContent
from netgrip.adapters.url_guard import acheck_url

MAX_REDIRECTS = 5
ACCEPTED = ("text/html", "application/xhtml+xml", "text/plain")
CHALLENGE_MARKERS = (
    "just a moment...",
    "cf-challenge",
    "attention required! | cloudflare",
    "checking your browser",
    "enable javascript and cookies to continue",
    "verify you are human",
    "g-recaptcha",
    "hcaptcha",
    "px-captcha",
    "ddos protection by",
)
CHALLENGE_MAX_BYTES = 20_000
Guard = Callable[[str], "str | None"]

Result = tuple[FetchAttempt, PageContent | None]


def looks_like_challenge(raw: bytes) -> bool:
    if len(raw) > CHALLENGE_MAX_BYTES:
        return False
    low = raw.decode("utf-8", errors="ignore").lower()
    return any(m in low for m in CHALLENGE_MARKERS)


def make_page(raw: bytes, url: str, content_type: str, limits: FetchLimits) -> Result:
    """Shared by the simple and the browser route: the extracted page, or why it is unusable."""
    if looks_like_challenge(raw):
        return FetchAttempt("simple", "blocked", "a challenge page"), None
    if "html" in content_type:
        ex = extract(raw, url)
        if len(ex.text) < limits.min_text_chars:
            return FetchAttempt(
                "simple", "error", "the page needs JavaScript to show its text"
            ), None
        return FetchAttempt("simple", "ok"), PageContent(
            url, raw, ex.text, ex.title, ex.published_at
        )
    text = raw.decode("utf-8", errors="replace").strip()
    return FetchAttempt("simple", "ok"), PageContent(url, raw, text, None, None)


async def fetch_simple(
    url: str,
    limits: FetchLimits = DEFAULT_LIMITS,
    *,
    guard=acheck_url,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Result:
    """One try on the simple route. Never raises for page-level trouble."""
    try:
        async with asyncio.timeout(limits.whole_s):
            return await _fetch(url, limits, guard, transport)
    except TimeoutError:
        return FetchAttempt("simple", "timeout", "the page took too long"), None
    except httpx.TimeoutException:
        return FetchAttempt("simple", "timeout", "the page took too long"), None
    except httpx.HTTPError as e:
        return FetchAttempt("simple", "error", f"{type(e).__name__} fetching the page"), None


async def _fetch(url: str, limits: FetchLimits, guard, transport) -> Result:
    timeout = httpx.Timeout(limits.read_s, connect=limits.navigation_s)
    headers = {"User-Agent": USER_AGENT, "Accept": ", ".join(ACCEPTED) + ";q=0.9,*/*;q=0.1"}
    async with httpx.AsyncClient(
        timeout=timeout, headers=headers, transport=transport, follow_redirects=False
    ) as client:
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            if (reason := await guard(current)) is not None:
                return FetchAttempt("simple", "error", f"refused: {reason}", final=True), None
            async with client.stream("GET", current) as resp:
                if resp.is_redirect and (loc := resp.headers.get("location")):
                    current = urljoin(str(resp.url), loc)
                    continue
                return await _read(resp, current, limits)
        return FetchAttempt("simple", "error", "too many redirects", final=True), None


async def _read(resp: httpx.Response, url: str, limits: FetchLimits) -> Result:
    status = resp.status_code
    if status in (401, 403, 429):
        return FetchAttempt("simple", "blocked", f"HTTP {status}"), None
    if status in (404, 410):
        return FetchAttempt("simple", "error", f"HTTP {status}", final=True), None
    if status >= 400:
        return FetchAttempt("simple", "error", f"HTTP {status}"), None
    ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype and ctype not in ACCEPTED:
        return FetchAttempt(
            "simple", "error", f"unsupported content type {ctype}", final=True
        ), None
    declared = resp.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limits.max_body:
        return _too_big(limits), None
    body = bytearray()
    async for chunk in resp.aiter_bytes():
        body += chunk
        if len(body) > limits.max_body:
            return _too_big(limits), None
    final_url = str(resp.url)
    if urlsplit(final_url).scheme not in ("http", "https"):
        final_url = url
    return make_page(bytes(body), final_url, ctype or "text/html", limits)


def _too_big(limits: FetchLimits) -> FetchAttempt:
    return FetchAttempt(
        "simple", "error", f"larger than {limits.max_body // (1024 * 1024)} MB", final=True
    )
