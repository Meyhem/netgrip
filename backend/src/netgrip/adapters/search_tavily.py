"""Tavily web search (tech spec section 4). Errors map onto the two `Search` errors; the key
is sent only in the Authorization header and never appears in a message or a log line."""

import logging
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

import httpx

from netgrip.adapters.model import redact
from netgrip.adapters.search import SearchHit, SearchRejected, SearchUnavailable

log = logging.getLogger(__name__)

ENDPOINT = "https://api.tavily.com"
TIMEOUT_SECONDS = 20.0
PRIMARY_HINT = " (official or original sources: primary documents, not commentary)"
_QUOTA_WORDS = ("usage limit", "quota", "credit", "plan limit", "exceeds your plan")


def _host_excluded(url: str, domains: list[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(
        host == d or host.endswith("." + d) for d in (x.lower().lstrip(".") for x in domains)
    )


def _detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        d = body.get("detail", body) if isinstance(body, dict) else body
        text = d.get("error", str(d)) if isinstance(d, dict) else str(d)
    except ValueError:
        text = resp.text
    return redact(text)[:300] or f"HTTP {resp.status_code}"


class TavilySearch:
    def __init__(
        self,
        get_key: Callable[[], Awaitable[str | None]],
        transport: httpx.AsyncBaseTransport | None = None,
        endpoint: str = ENDPOINT,
    ) -> None:
        self._get_key = get_key
        self._endpoint = endpoint.rstrip("/")
        self._http = httpx.AsyncClient(transport=transport, timeout=TIMEOUT_SECONDS)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def check(self) -> tuple[bool, str | None]:
        """Whether the stored key is accepted, using the cheapest query."""
        try:
            await self.search("test", max_results=1, exclude_domains=[], prefer="none")
        except SearchRejected as e:
            if e.kind in ("key", "credit"):
                return False, e.message
            return True, None
        except SearchUnavailable as e:
            raise e
        return True, None

    async def search(
        self, query: str, *, max_results: int, exclude_domains: list[str], prefer: str
    ) -> list[SearchHit]:
        key = await self._get_key()
        if not key:
            raise SearchRejected("key", "No search key is set")
        body = {
            "query": query + (PRIMARY_HINT if prefer == "primary" else ""),
            "max_results": max_results,
            "search_depth": "basic",
            "exclude_domains": exclude_domains,
        }
        try:
            resp = await self._http.post(
                f"{self._endpoint}/search", json=body, headers={"Authorization": f"Bearer {key}"}
            )
        except httpx.HTTPError as e:
            raise SearchUnavailable(f"{type(e).__name__} calling the search provider") from None
        status = resp.status_code
        if status in (401, 403):
            raise SearchRejected("key", _detail(resp))
        if status == 432 or (
            status == 429 and any(w in _detail(resp).lower() for w in _QUOTA_WORDS)
        ):
            raise SearchRejected("credit", _detail(resp))
        if status == 429 or status >= 500:
            raise SearchUnavailable(f"The search provider answered {status}")
        if status >= 400:
            raise SearchRejected("request", _detail(resp))
        try:
            results = resp.json()["results"]
            hits = [
                SearchHit(
                    url=r["url"],
                    title=r.get("title") or r["url"],
                    snippet=r.get("content") or "",
                    published_at=r.get("published_date"),
                )
                for r in results
            ]
        except (ValueError, KeyError, TypeError):
            raise SearchUnavailable("Unexpected response from the search provider") from None
        return [h for h in hits if not _host_excluded(h.url, exclude_domains)][:max_results]
