"""The page fetch interface. A fetcher never raises for page-level trouble (E5)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

Route = Literal["simple", "browser", "hardened"]
Outcome = Literal["ok", "timeout", "blocked", "error"]
ROUTES: tuple[Route, ...] = ("simple", "browser", "hardened")


@dataclass(frozen=True)
class FetchAttempt:
    route: Route
    outcome: Outcome
    error: str | None = None
    # Another route would not help (a refused URL, a binary file, a page that is gone).
    final: bool = False


@dataclass(frozen=True)
class PageContent:
    final_url: str
    raw: bytes
    text: str
    title: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class FetchResult:
    status: Literal["ok", "unobtainable"]
    page: PageContent | None = None
    attempts: list[FetchAttempt] = field(default_factory=list)


# on_attempt(n, total, attempt): called with attempt=None as attempt n of total starts, and
# again with the finished attempt.
OnAttempt = Callable[[int, int, FetchAttempt | None], Awaitable[None]]


class Fetcher(Protocol):
    async def fetch(self, url: str, *, on_attempt: OnAttempt) -> FetchResult: ...
