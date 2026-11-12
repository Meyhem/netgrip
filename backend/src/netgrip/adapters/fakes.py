"""A scripted ModelClient for tests and NETGRIP_FAKE=1. Never touches the network."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import jsonschema

from netgrip.adapters.fetcher import (
    ROUTES,
    FetchAttempt,
    FetchResult,
    OnAttempt,
    PageContent,
)
from netgrip.adapters.model import (
    ModelMalformed,
    ModelRejected,
    ModelRequest,
    ModelResponse,
    ModelUnavailable,
    ToolCall,
    Usage,
)
from netgrip.adapters.search import SearchHit, SearchRejected, SearchUnavailable

SCENARIOS = Path(__file__).parent / "fake_scenarios"


class FakeModelClient:
    """`script` maps a purpose (or "purpose:node_ref") to a queue of entries. An entry is
    `{"raise": "unavailable"|"malformed"|"key"|"credit"|"request"}` or a response with any of
    `text`, `parsed`, `tool_calls`, `usage`. A "malformed" entry with `usage`, or an answer that
    fails the request's `response_schema`, raises ModelMalformed carrying that usage. With
    `repeat_last`, an exhausted queue repeats its last entry; otherwise asking again raises
    LookupError."""

    def __init__(self, script: dict, repeat_last: bool = False) -> None:
        self.queues: dict[str, list[dict]] = {k: list(v) for k, v in script.items()}
        self.repeat_last = repeat_last
        self.calls: list[ModelRequest] = []
        self._last: dict[str, dict] = {}

    @classmethod
    def from_scenario(cls, name: str, repeat_last: bool = False) -> "FakeModelClient":
        script = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))
        return cls(script, repeat_last=repeat_last)

    def _next(self, req: ModelRequest) -> dict:
        keys = [f"{req.purpose}:{req.node_ref}"] if req.node_ref else []
        key = next((k for k in [*keys, req.purpose] if k in self.queues), req.purpose)
        queue = self.queues.get(key)
        if queue:
            self._last[key] = entry = queue.pop(0)
            return entry
        if self.repeat_last and key in self._last:
            return self._last[key]
        raise LookupError(f"fake model script has no entry left for {key!r}")

    async def complete(self, req: ModelRequest) -> ModelResponse:
        self.calls.append(req)
        entry = self._next(req)
        usage = {"tokens_in": 100, "tokens_out": 200, "cost_usd": "0.01"} | entry.get("usage", {})
        if usage["cost_usd"] is not None:
            usage["cost_usd"] = Decimal(str(usage["cost_usd"]))
        match entry.get("raise"):
            case None:
                pass
            case "unavailable":
                raise ModelUnavailable("fake: unavailable")
            case "malformed":
                raise ModelMalformed(
                    "fake: malformed", Usage(**usage) if "usage" in entry else None
                )
            case "key" | "credit" | "request" as kind:
                raise ModelRejected(kind, f"fake: {kind} rejected")
            case other:
                raise ValueError(f"unknown fake failure {other!r}")
        parsed = entry.get("parsed")
        text = entry.get("text", json.dumps(parsed) if parsed is not None else "")
        if req.response_schema is not None:
            try:
                answer = parsed if parsed is not None else json.loads(text)
                jsonschema.validate(answer, req.response_schema)
            except (ValueError, jsonschema.ValidationError) as e:
                raise ModelMalformed(
                    "fake: answer does not satisfy the schema", Usage(**usage)
                ) from e
        return ModelResponse(
            text=text,
            parsed=parsed,
            tool_calls=[ToolCall(**c) for c in entry.get("tool_calls", [])],
            usage=Usage(**usage),
        )

    async def stream(self, req: ModelRequest) -> AsyncIterator[str | ModelResponse]:
        resp = await self.complete(req)
        if resp.text:
            yield resp.text
        yield resp

    async def check(self) -> None:
        return None


class FakeSearch:
    """`fixtures`: {"results": [{"match": substring of the query, "hits": [...]} or
    {"match": ..., "raise": "unavailable" | "key" | "credit" | "request"}], "default": [hits]}.
    The first matching entry wins; no match gives `default`."""

    def __init__(self, fixtures: dict) -> None:
        self.fixtures = fixtures
        self.calls: list[str] = []

    @classmethod
    def from_scenario(cls, name: str) -> "FakeSearch":
        path = SCENARIOS / name / "search.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    async def search(
        self, query: str, *, max_results: int, exclude_domains: list[str], prefer: str
    ) -> list[SearchHit]:
        self.calls.append(query)
        entry = next(
            (e for e in self.fixtures.get("results", []) if e["match"].lower() in query.lower()),
            {"hits": self.fixtures.get("default", [])},
        )
        match entry.get("raise"):
            case None:
                pass
            case "unavailable":
                raise SearchUnavailable("fake: unavailable")
            case kind:
                raise SearchRejected(kind, f"fake: {kind} rejected")
        hits = [SearchHit(**{"published_at": None, **h}) for h in entry["hits"]]
        hits = [h for h in hits if not any(d in h.url for d in exclude_domains)]
        return hits[:max_results]


class FakeFetcher:
    """`fixtures`: {url: spec}. A spec has `text` (and optional `title`, `published_at`, `raw`),
    and `attempts`, the outcomes of successive tries (default ["ok"]): "timeout", "blocked",
    "error" or "ok", tried on the simple, browser and hardened routes in turn. `unobtainable`
    is shorthand for three blocked tries. An unknown URL is unobtainable. `delay` seconds are
    awaited per fetch, so tests can overlap calls."""

    def __init__(self, fixtures: dict, delay: float = 0.0) -> None:
        self.fixtures = fixtures
        self.delay = delay
        self.calls: list[str] = []

    @classmethod
    def from_scenario(cls, name: str) -> "FakeFetcher":
        path = SCENARIOS / name / "pages.json"
        return cls(json.loads(path.read_text(encoding="utf-8")))

    async def fetch(self, url: str, *, on_attempt: OnAttempt) -> FetchResult:
        import asyncio

        self.calls.append(url)
        if self.delay:
            await asyncio.sleep(self.delay)
        spec = self.fixtures.get(url, {"unobtainable": True})
        outcomes = (
            ["blocked"] * len(ROUTES) if spec.get("unobtainable") else spec.get("attempts", ["ok"])
        )
        attempts: list[FetchAttempt] = []
        total = len(ROUTES)
        for n, (route, outcome) in enumerate(zip(ROUTES, outcomes, strict=False), start=1):
            await on_attempt(n, total, None)
            attempt = FetchAttempt(route, outcome, None if outcome == "ok" else f"fake: {outcome}")
            attempts.append(attempt)
            await on_attempt(n, total, attempt)
            if outcome == "ok":
                text = spec["text"]
                raw = spec.get("raw", text).encode("utf-8")
                page = PageContent(
                    final_url=url,
                    raw=raw,
                    text=text,
                    title=spec.get("title"),
                    published_at=spec.get("published_at"),
                )
                return FetchResult("ok", page, attempts)
        return FetchResult("unobtainable", None, attempts)
