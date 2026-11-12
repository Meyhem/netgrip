"""The model client interface (D-xx): one request/response shape for every provider."""

import re
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

Tier = Literal["strong", "standard", "fast", "verifier"]


class ToolSpec(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class Message(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None  # on an assistant message
    tool_call_id: str | None = None  # on a tool message


class ModelRequest(BaseModel):
    purpose: str
    tier: Tier
    model: str
    system: str
    messages: list[Message]
    tools: list[ToolSpec] | None = None
    response_schema: dict | None = None
    node_ref: str | None = None


class Usage(BaseModel):
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: Decimal | None = None  # None: the provider did not say


class ModelResponse(BaseModel):
    text: str = ""
    parsed: dict | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)


class ModelError(Exception):
    pass


class ModelUnavailable(ModelError):
    """Timeouts, 5xx, 429: try again later."""


class ModelRejected(ModelError):
    """The provider refused: the key (401/403), the credit (402) or the request itself (any
    other 4xx, e.g. an unknown model or a context that is too long). Retrying will not help.
    Only "key" is a verdict on the key."""

    def __init__(self, kind: Literal["key", "credit", "request"], message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


class ModelMalformed(ModelError):
    """The answer does not satisfy the requested schema. `usage` is set when an answer was
    received and the provider reported its usage: that call was paid for (B5)."""

    def __init__(self, message: str, usage: "Usage | None" = None) -> None:
        super().__init__(message)
        self.usage = usage


class ModelClient(Protocol):
    async def complete(self, req: ModelRequest) -> ModelResponse: ...

    def stream(self, req: ModelRequest) -> AsyncIterator[str | ModelResponse]:
        """Text deltas, then the complete ModelResponse as the last item."""
        ...

    async def check(self) -> None:
        """Raise ModelRejected / ModelUnavailable if the key does not work."""
        ...


_SECRET = re.compile(r"sk-[A-Za-z0-9_\-]+|[A-Za-z0-9_\-]{20,}")


def redact(text: str) -> str:
    """`text` with anything that looks like a key or token replaced: provider error messages
    sometimes echo the key back."""
    return _SECRET.sub("[redacted]", text)
