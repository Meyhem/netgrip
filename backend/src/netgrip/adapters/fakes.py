"""A scripted ModelClient for tests and NETGRIP_FAKE=1. Never touches the network."""

import json
from collections.abc import AsyncIterator
from decimal import Decimal
from pathlib import Path

import jsonschema

from netgrip.adapters.model import (
    ModelMalformed,
    ModelRejected,
    ModelRequest,
    ModelResponse,
    ModelUnavailable,
    ToolCall,
    Usage,
)

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
