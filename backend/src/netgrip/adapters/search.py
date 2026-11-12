"""The web search interface. Providers raise only the two errors below."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SearchHit:
    url: str
    title: str
    snippet: str
    published_at: str | None = None


class SearchError(Exception):
    pass


class SearchUnavailable(SearchError):
    """The provider is down or unreachable: the run pauses (N-05)."""


class SearchRejected(SearchError):
    """The provider refused the request: kind is e.g. "key", "credit" or "request"."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class Search(Protocol):
    async def search(
        self, query: str, *, max_results: int, exclude_domains: list[str], prefer: str
    ) -> list[SearchHit]: ...
