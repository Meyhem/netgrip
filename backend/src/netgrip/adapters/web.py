"""The real web adapters wired together: Tavily, the escalating fetcher and its browser pools."""

import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from netgrip.adapters.browser_pool import BrowserPool, PoolHealth
from netgrip.adapters.fetch_escalating import EscalatingFetcher
from netgrip.adapters.fetch_limits import DEFAULT_LIMITS, FetchLimits
from netgrip.adapters.politeness import Politeness
from netgrip.adapters.search_tavily import TavilySearch
from netgrip.engine.limiter import Limiter

log = logging.getLogger(__name__)


class Web:
    def __init__(
        self,
        profile_dir: Path,
        get_search_key: Callable[[], Awaitable[str | None]],
        browser_pages: int = 4,
        politeness_s: float = 2.0,
        limits: FetchLimits = DEFAULT_LIMITS,
    ) -> None:
        self.search = TavilySearch(get_search_key)
        self.politeness = Politeness(politeness_s)
        slots = Limiter("browser", browser_pages)  # one limit for both pools (R-03)
        self.slots = slots
        self.pool = BrowserPool(browser_pages, limits, profile_dir / "standard", slots=slots)
        self.hardened = BrowserPool(
            browser_pages, limits, profile_dir / "hardened", hardened=True, slots=slots
        )
        self.fetcher = EscalatingFetcher(self.politeness, self.pool, self.hardened, limits)

    async def start(self) -> None:
        """Remove what a previous run left behind. Browsers start on first use."""
        await self.pool.sweep()
        await self.hardened.sweep()

    async def stop(self) -> None:
        await self.pool.stop()
        await self.hardened.stop()
        await self.search.aclose()

    def apply(self, capacity, politeness_s: float) -> None:
        self.slots.resize(capacity.browser_pages)
        self.politeness.set_interval(politeness_s)

    def health(self) -> PoolHealth:
        a, b = self.pool.health(), self.hardened.health()
        return PoolHealth(
            a.open_pages + b.open_pages, a.browsers + b.browsers,
            a.restarts_today + b.restarts_today,
            a.fetches_timed_out_today + b.fetches_timed_out_today,
        )  # fmt: skip

    @property
    def limit(self) -> int:
        return self.slots.capacity
