"""ModelClient for any OpenAI-compatible chat-completions endpoint (OpenRouter by default).

The key is fetched per call and used only in the Authorization header: it is never logged,
never put in an exception message, never kept on the client."""

import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit

import httpx
import jsonschema

from netgrip.adapters.model import (
    ModelMalformed,
    ModelRejected,
    ModelRequest,
    ModelResponse,
    ModelUnavailable,
    ToolCall,
    Usage,
    redact,
)
from netgrip.boundary.events import utc_now_iso
from netgrip.store.settings import KeyStatus

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 120.0

BaseUrl = str | Callable[[], Awaitable[str]]


def _cost(raw) -> Decimal | None:
    """The provider's cost, or None if it gave none or something that is not a finite number
    (then the price table or an approximate amount is used instead)."""
    if raw is None or isinstance(raw, bool):
        return None
    try:
        cost = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        log.warning("ignoring an unreadable usage.cost from the model provider")
        return None
    return cost if cost.is_finite() else None


def _usage(raw: dict | None) -> Usage:
    raw = raw or {}
    return Usage(
        tokens_in=int(raw.get("prompt_tokens") or 0),
        tokens_out=int(raw.get("completion_tokens") or 0),
        cost_usd=_cost(raw.get("cost")),
    )


def _error_message(resp: httpx.Response) -> str:
    try:
        err = resp.json().get("error")
        msg = err.get("message") if isinstance(err, dict) else err
    except (ValueError, AttributeError):
        msg = None
    return redact(str(msg))[:300] if msg else f"HTTP {resp.status_code}"


def _raise_for_status(resp: httpx.Response) -> None:
    code = resp.status_code
    if code < 400:
        return
    if code in (401, 403):
        raise ModelRejected("key", _error_message(resp))
    if code == 402:
        raise ModelRejected("credit", _error_message(resp))
    if code in (408, 429) or code >= 500:
        raise ModelUnavailable(_error_message(resp))
    raise ModelRejected("request", _error_message(resp))


def _message_to_wire(m) -> dict:
    out: dict[str, Any] = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in m.tool_calls
        ]
    if m.tool_call_id:
        out["tool_call_id"] = m.tool_call_id
    return out


def _tool_calls(raw: list[dict] | None) -> list[ToolCall]:
    calls = []
    for c in raw or []:
        fn = c.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except ValueError as e:
            raise ModelMalformed("tool call arguments are not JSON") from e
        calls.append(ToolCall(id=c.get("id", ""), name=fn.get("name", ""), arguments=args))
    return calls


def _finish(req: ModelRequest, text: str, tool_calls: list[ToolCall], usage: Usage):
    """A malformed answer raises ModelMalformed carrying `usage`: it was still paid for."""
    parsed = None
    if req.response_schema is not None:
        try:
            parsed = json.loads(text)
            jsonschema.validate(parsed, req.response_schema)
        except (ValueError, jsonschema.ValidationError) as e:
            raise ModelMalformed(
                f"answer does not satisfy the schema ({req.purpose})", usage
            ) from e
        if not isinstance(parsed, dict):
            raise ModelMalformed("answer is not a JSON object", usage)
    return ModelResponse(text=text, parsed=parsed, tool_calls=tool_calls, usage=usage)


class OpenAICompatClient:
    def __init__(
        self,
        base_url: BaseUrl,
        get_key: Callable[[], Awaitable[str | None]],
        transport: httpx.AsyncBaseTransport | None = None,
        get_routing: Callable[[], Awaitable[Any]] | None = None,
    ) -> None:
        self._base_url = base_url
        self._get_key = get_key
        self._get_routing = get_routing
        self._catalogue: tuple[str, float, list[dict]] | None = None  # (base, fetched at, rows)
        self._http = httpx.AsyncClient(transport=transport, timeout=TIMEOUT_SECONDS)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _url(self, path: str) -> str:
        return (await self._base()).rstrip("/") + path

    async def _headers(self) -> dict[str, str]:
        key = await self._get_key()
        if not key:
            raise ModelRejected("key", "No model key is set")
        return {"Authorization": f"Bearer {key}"}

    async def _base(self) -> str:
        return self._base_url if isinstance(self._base_url, str) else await self._base_url()

    async def _body(self, req: ModelRequest, stream: bool) -> dict:
        body = self._payload(req, stream)
        if self._get_routing is not None and is_openrouter(await self._base()):
            if provider := provider_preferences(await self._get_routing()):
                body["provider"] = provider
        return body

    def _payload(self, req: ModelRequest, stream: bool) -> dict:
        body: dict[str, Any] = {
            "model": req.model,
            "messages": [{"role": "system", "content": req.system}]
            + [_message_to_wire(m) for m in req.messages],
        }
        if req.tools:
            body["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in req.tools
            ]
        if req.response_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "answer", "strict": True, "schema": req.response_schema},
            }
        if stream:
            body["stream"] = True
            body["stream_options"] = {"include_usage": True}
        return body

    async def complete(self, req: ModelRequest) -> ModelResponse:
        log.debug("model call: purpose=%s model=%s", req.purpose, req.model)
        try:
            resp = await self._http.post(
                await self._url("/chat/completions"),
                json=await self._body(req, stream=False),
                headers=await self._headers(),
            )
        except httpx.HTTPError as e:
            raise ModelUnavailable(f"{type(e).__name__} calling the model") from None
        _raise_for_status(resp)
        try:
            data = resp.json()
        except ValueError as e:
            raise ModelMalformed("unexpected response from the model endpoint") from e
        usage = None
        if isinstance(data, dict) and isinstance(data.get("usage"), dict):
            usage = _usage(data["usage"])
        try:
            message = data["choices"][0]["message"]
            tool_calls = _tool_calls(message.get("tool_calls"))
        except (KeyError, IndexError, TypeError, AttributeError) as e:
            raise ModelMalformed("unexpected response from the model endpoint", usage) from e
        except ModelMalformed as e:
            e.usage = e.usage or usage
            raise
        return _finish(req, message.get("content") or "", tool_calls, usage or Usage())

    async def stream(self, req: ModelRequest) -> AsyncIterator[str | ModelResponse]:
        log.debug("model stream: purpose=%s model=%s", req.purpose, req.model)
        parts: list[str] = []
        usage = Usage()
        try:
            async with self._http.stream(
                "POST",
                await self._url("/chat/completions"),
                json=await self._body(req, stream=True),
                headers=await self._headers(),
            ) as resp:
                if resp.status_code >= 400:
                    await resp.aread()
                _raise_for_status(resp)
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                    except ValueError:
                        continue
                    if data.get("usage"):
                        usage = _usage(data["usage"])
                    for choice in data.get("choices", []):
                        delta = choice.get("delta", {}).get("content")
                        if delta:
                            parts.append(delta)
                            yield delta
        except httpx.HTTPError as e:
            raise ModelUnavailable(f"{type(e).__name__} calling the model") from None
        yield _finish(req, "".join(parts), [], usage)

    async def check(self) -> None:
        try:
            resp = await self._http.get(await self._url("/models"), headers=await self._headers())
        except httpx.HTTPError as e:
            raise ModelUnavailable(f"{type(e).__name__} reaching the model endpoint") from None
        _raise_for_status(resp)

    async def list_models(self) -> list[dict]:
        """The provider's model catalogue, for pickers: id, name and USD per million tokens
        (None when the provider lists no price). `/models` is public on OpenRouter, so a key
        is sent only if there is one."""
        base = await self._base()
        if (
            self._catalogue
            and self._catalogue[0] == base
            and time.monotonic() - self._catalogue[1] < CATALOGUE_TTL_SECONDS
        ):
            return self._catalogue[2]
        headers: dict[str, str] = {}
        if key := await self._get_key():
            headers["Authorization"] = f"Bearer {key}"
        try:
            resp = await self._http.get(await self._url("/models"), headers=headers)
        except httpx.HTTPError as e:
            raise ModelUnavailable(f"{type(e).__name__} reaching the model endpoint") from None
        _raise_for_status(resp)
        try:
            rows = resp.json()["data"]
            models = sorted(
                (_catalogue_entry(r) for r in rows if isinstance(r, dict) and r.get("id")),
                key=lambda m: m["id"],
            )
        except (ValueError, KeyError, TypeError) as e:
            raise ModelMalformed("unexpected response from the model endpoint") from e
        self._catalogue = (base, time.monotonic(), models)
        return models


CATALOGUE_TTL_SECONDS = 600


def is_openrouter(base_url: str) -> bool:
    host = urlsplit(base_url).hostname or ""
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


def provider_preferences(routing: Any) -> dict:
    """OpenRouter's `provider` request field from the routing setting; empty when it is all
    defaults, so OpenRouter balances providers as it normally does."""
    if routing is None:
        return {}
    r = routing if isinstance(routing, dict) else routing.model_dump()
    out: dict[str, Any] = {}
    if r.get("sort") in ("price", "throughput", "latency"):
        out["sort"] = r["sort"]
    if r.get("deny_data_collection"):
        out["data_collection"] = "deny"
    if r.get("zero_retention"):
        out["zdr"] = True
    return out


def _per_million(value: Any) -> float | None:
    try:
        n = float(value) * 1_000_000
    except (TypeError, ValueError):
        return None
    return round(n, 4) if n > 0 else None


def _catalogue_entry(row: dict) -> dict:
    pricing = row.get("pricing") or {}
    return {
        "id": row["id"],
        "name": row.get("name") or row["id"],
        "price_in_per_m": _per_million(pricing.get("prompt")),
        "price_out_per_m": _per_million(pricing.get("completion")),
        "context_length": row.get("context_length")
        if isinstance(row.get("context_length"), int)
        else None,
    }


async def check_model_key(client) -> KeyStatus:
    """Ask the provider whether the key works. A rejection of the key or the credit is a
    verdict on the key; an unreachable provider or a refused request is not, so the key stays
    as it was. Messages are redacted: providers sometimes echo the key back."""
    try:
        await client.check()
    except ModelRejected as e:
        if e.kind == "request":
            return KeyStatus(
                set=True,
                status="set",
                checked_at=utc_now_iso(),
                message=f"Not checked: {redact(e.message)}",
            )
        return KeyStatus(
            set=True, status="rejected", checked_at=utc_now_iso(), message=redact(e.message)
        )
    except ModelUnavailable as e:
        return KeyStatus(
            set=True,
            status="set",
            checked_at=utc_now_iso(),
            message=f"Not checked: {redact(str(e))}",
        )
    return KeyStatus(set=True, status="set", checked_at=utc_now_iso())
