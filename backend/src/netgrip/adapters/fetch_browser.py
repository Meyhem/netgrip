"""The browser fetch route (W2): a page rendered in a borrowed browser session."""

import asyncio
import logging

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Route as PwRoute

from netgrip.adapters.browser_pool import BrowserFault, BrowserPool
from netgrip.adapters.fetch_http import make_page
from netgrip.adapters.fetch_limits import DEFAULT_LIMITS, FetchLimits
from netgrip.adapters.fetcher import FetchAttempt, PageContent, Route
from netgrip.adapters.url_guard import acheck_url

log = logging.getLogger(__name__)
BLOCKED_RESOURCES = {"image", "media", "font"}
_TEXT_READY = "() => !!document.body && document.body.innerText.trim().length >= %d"


async def fetch_browser(
    pool: BrowserPool,
    url: str,
    limits: FetchLimits = DEFAULT_LIMITS,
    *,
    guard=acheck_url,
    route: Route | None = None,
) -> tuple[FetchAttempt, PageContent | None]:
    """One try. Never raises for page-level trouble or a browser fault (both are outcomes),
    but cancellation propagates after the session is closed."""
    route = route or ("hardened" if pool.hardened else "browser")
    try:
        async with asyncio.timeout(limits.whole_s):
            return await _fetch(pool, url, limits, guard, route)
    except TimeoutError:
        pool.note_timeout()
        return FetchAttempt(route, "timeout", "the page took too long"), None
    except BrowserFault as e:
        return FetchAttempt(route, "error", f"browser fault: {e}"), None


async def _fetch(pool, url, limits, guard, route) -> tuple[FetchAttempt, PageContent | None]:
    async with pool.session() as page:

        async def handle(r: PwRoute) -> None:
            req = r.request
            if req.resource_type in BLOCKED_RESOURCES:
                await r.abort()
            elif (reason := await guard(req.url)) is not None:
                log.info("browser request refused: %s", reason)
                await r.abort("blockedbyclient")
            else:
                await r.continue_()

        await page.route("**/*", handle)
        try:
            resp = await page.goto(
                url, wait_until="domcontentloaded", timeout=limits.navigation_s * 1000
            )
            status = resp.status if resp else 0
            if status in (401, 403, 429):
                return FetchAttempt(route, "blocked", f"HTTP {status}"), None
            if status in (404, 410):
                return FetchAttempt(route, "error", f"HTTP {status}", final=True), None
            if status >= 400:
                return FetchAttempt(route, "error", f"HTTP {status}"), None
            ctype = ((resp.headers.get("content-type") if resp else "") or "").split(";")[0]
            if ctype and "html" not in ctype and not ctype.startswith("text/"):
                return FetchAttempt(
                    route, "error", f"unsupported content type {ctype}", final=True
                ), None
            try:  # content wait: JavaScript pages fill in their text after the first load
                await page.wait_for_function(
                    _TEXT_READY % limits.min_text_chars, timeout=limits.content_wait_s * 1000
                )
            except PlaywrightError as e:
                if "Timeout" not in str(e):
                    raise
            html = await asyncio.wait_for(page.content(), limits.read_s)
            final_url = page.url
        except PlaywrightError as e:
            msg = str(e)
            if "Timeout" in msg:
                pool.note_timeout()
                return FetchAttempt(route, "timeout", "the page took too long"), None
            if "ERR_BLOCKED_BY_CLIENT" in msg:
                return FetchAttempt(
                    route, "error", "refused: not a public address", final=True
                ), None
            if "crashed" in msg.lower():
                return FetchAttempt(route, "error", "the page crashed"), None
            if "closed" in msg.lower() or "disconnected" in msg.lower():
                raise BrowserFault("the browser closed under the fetch") from None
            return FetchAttempt(route, "error", "navigation failed"), None
        return make_page(html.encode("utf-8"), final_url, "text/html", limits, route)
