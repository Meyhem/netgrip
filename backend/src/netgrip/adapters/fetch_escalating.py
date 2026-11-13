"""The escalating fetcher (W1–W3): simple, then browser, then hardened browser."""

import asyncio
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

from netgrip.adapters.browser_pool import BrowserFault, BrowserPool
from netgrip.adapters.fetch_browser import fetch_browser
from netgrip.adapters.fetch_http import fetch_simple
from netgrip.adapters.fetch_limits import DEFAULT_LIMITS, FetchLimits
from netgrip.adapters.fetcher import (
    ROUTES,
    FetchAttempt,
    FetchResult,
    OnAttempt,
    PageContent,
    Route,
)
from netgrip.adapters.politeness import Politeness
from netgrip.engine.clock import Clock, SystemClock

RouteFn = Callable[[str], Awaitable[tuple[FetchAttempt, PageContent | None]]]


class EscalatingFetcher:
    def __init__(
        self,
        politeness: Politeness,
        pool: BrowserPool | None,
        hardened_pool: BrowserPool | None,
        limits: FetchLimits = DEFAULT_LIMITS,
        clock: Clock | None = None,
        *,
        routes: dict[Route, RouteFn] | None = None,
    ) -> None:
        self.politeness = politeness
        self.limits = limits
        self.clock = clock or SystemClock()
        self.routes: dict[Route, RouteFn] = {
            "simple": lambda url: fetch_simple(url, limits),
        }
        if pool is not None:
            self.routes["browser"] = lambda url: fetch_browser(pool, url, limits)
        if hardened_pool is not None:
            self.routes["hardened"] = lambda url: fetch_browser(hardened_pool, url, limits)
        self.routes.update(routes or {})

    async def fetch(self, url: str, *, on_attempt: OnAttempt) -> FetchResult:
        host = urlsplit(url).hostname or ""
        routes = [r for r in ROUTES if r in self.routes]
        per_route = max(1, self.limits.attempts_per_route)
        total = len(routes) * per_route
        attempts: list[FetchAttempt] = []
        n = 0
        retries = 0
        for route in routes:
            for k in range(per_route):
                n += 1
                await self.politeness.wait(host)
                await on_attempt(n, total, None)
                attempt, page = await self._try(route, url)
                attempts.append(attempt)
                await on_attempt(n, total, attempt)
                if attempt.outcome == "ok" and page is not None:
                    return FetchResult("ok", page, attempts)
                if attempt.final:
                    return FetchResult("unobtainable", None, attempts)
                if attempt.outcome == "blocked":
                    break  # retrying a refusal on the same route only annoys the site
                if k + 1 < per_route:
                    await self.clock.sleep(self.limits.delay_before(retries + 2))
                    retries += 1
        return FetchResult("unobtainable", None, attempts)

    async def _try(self, route: Route, url: str) -> tuple[FetchAttempt, PageContent | None]:
        try:
            return await self.routes[route](url)
        except BrowserFault as e:
            return FetchAttempt(route, "error", f"browser fault: {e}"), None
        except asyncio.CancelledError:
            raise
        except Exception as e:  # a route must not fail a node (E5)
            return FetchAttempt(route, "error", f"{type(e).__name__} fetching the page"), None
