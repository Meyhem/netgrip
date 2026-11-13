"""A scripted ModelClient for tests and NETGRIP_FAKE=1. Never touches the network."""

import asyncio
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
from netgrip.adapters.schema import fill_nulls, strict_problems
from netgrip.adapters.search import SearchHit, SearchRejected, SearchUnavailable

SCENARIOS = Path(__file__).parent / "fake_scenarios"


class FakeModelClient:
    """`script` maps a purpose, "purpose:node_ref" or "purpose@text" to a queue of entries.
    A request takes the "purpose:node_ref" queue if scripted, else the first "purpose@text"
    queue (in script order) whose text occurs in its messages, else the purpose's queue; so a
    scenario can answer per node ("node.decide@Your task: ...") or per page. An entry is
    `{"raise": "unavailable"|"malformed"|"key"|"credit"|"request"}` or a response with any of
    `text`, `parsed`, `tool_calls`, `usage`. A "malformed" entry with `usage`, or an answer that
    fails the request's `response_schema`, raises ModelMalformed carrying that usage. With
    `repeat_last`, an exhausted queue repeats its last entry; otherwise asking again raises
    LookupError. With `per_investigation`, each investigation (`req.investigation_id`) is
    served the whole script from the start, so every fake run in one process is the same."""

    def __init__(
        self,
        script: dict,
        repeat_last: bool = False,
        per_investigation: bool = False,
        delay_s: float = 0.0,
    ) -> None:
        self.queues: dict[str, list[dict]] = {k: list(v) for k, v in script.items()}
        self.repeat_last = repeat_last
        self.per_investigation = per_investigation
        self.delay_s = delay_s  # opt-in latency per call (NETGRIP_FAKE_DELAY_MS), default none
        self.calls: list[ModelRequest] = []
        self._last: dict[str, dict] = {}
        self._script = {k: list(v) for k, v in script.items()}
        self._each: dict[str | None, tuple[dict[str, list[dict]], dict[str, dict]]] = {}

    @classmethod
    def from_scenario(
        cls,
        name: str,
        repeat_last: bool = False,
        per_investigation: bool = False,
        delay_s: float = 0.0,
    ) -> "FakeModelClient":
        script = json.loads((SCENARIOS / f"{name}.json").read_text(encoding="utf-8"))
        return cls(script, repeat_last, per_investigation, delay_s)

    def _next(self, req: ModelRequest) -> dict:
        if not self.per_investigation:
            return self._pop(req, self.queues, self._last)
        if req.investigation_id not in self._each:
            fresh = {k: list(v) for k, v in self._script.items()}
            self._each[req.investigation_id] = (fresh, {})
        return self._pop(req, *self._each[req.investigation_id])

    def _pop(self, req: ModelRequest, queues: dict[str, list[dict]], last: dict) -> dict:
        keys = [f"{req.purpose}:{req.node_ref}"] if req.node_ref else []
        prompt = "\n".join(m.content or "" for m in req.messages)
        keys += [
            k for k in queues if k.startswith(f"{req.purpose}@") and k.split("@", 1)[1] in prompt
        ]
        key = next((k for k in [*keys, req.purpose] if k in queues), req.purpose)
        queue = queues.get(key)
        if queue:
            last[key] = entry = queue.pop(0)
            return entry
        if self.repeat_last and key in last:
            return last[key]
        raise LookupError(f"fake model script has no entry left for {key!r}")

    async def complete(self, req: ModelRequest) -> ModelResponse:
        self.calls.append(req)
        if req.response_schema is not None and (bad := strict_problems(req.response_schema)):
            # The real adapter sends "strict": true; such a schema would be refused there.
            raise AssertionError(f"{req.purpose}: schema not strict-valid: {bad}")
        entry = self._next(req)
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
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
                # A strict provider answers every field: omitted optional ones come as null.
                answer = fill_nulls(answer, req.response_schema)
                jsonschema.validate(answer, req.response_schema)
            except (ValueError, jsonschema.ValidationError) as e:
                raise ModelMalformed(
                    "fake: answer does not satisfy the schema", Usage(**usage)
                ) from e
            parsed, text = answer, json.dumps(answer)
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
