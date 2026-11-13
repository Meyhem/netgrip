"""Deadlines and limits of web acquisition (A-09)."""

from dataclasses import dataclass

MB = 1024 * 1024


@dataclass(frozen=True)
class FetchLimits:
    navigation_s: float = 20.0
    content_wait_s: float = 10.0
    read_s: float = 10.0
    whole_s: float = 45.0
    attempts_per_route: int = 2
    retry_delays_s: tuple[float, ...] = (2.0, 6.0)
    max_body: int = 5 * MB
    recycle_pages: int = 50
    recycle_minutes: float = 30.0
    close_s: float = 5.0  # closing a browser context
    ping_s: float = 5.0  # a browser that does not answer within this is dead
    min_text_chars: int = 200  # less than this after extraction: the page needs JavaScript

    def delay_before(self, attempt: int) -> float:
        """Delay before attempt `attempt` (2 for the first retry)."""
        i = min(max(attempt - 2, 0), len(self.retry_delays_s) - 1)
        return self.retry_delays_s[i]


DEFAULT_LIMITS = FetchLimits()
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
