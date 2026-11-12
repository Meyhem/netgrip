"""In-process fan-out of durable events and ephemeral messages to live subscribers."""

import asyncio
from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from netgrip.boundary.events import Event


class Ephemeral(BaseModel):
    """Streamed model text and similar. No sequence number; never stored or replayed (D-11)."""

    investigation_id: str
    node_id: str | None = None
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


_CLOSED = object()


class Subscription:
    """Registered on creation, so nothing published after construction is missed."""

    def __init__(self, bus: "EventBus", investigation_id: str) -> None:
        self._bus = bus
        self.investigation_id = investigation_id
        self._queue: asyncio.Queue = asyncio.Queue()
        bus._subs[investigation_id].add(self)

    def _put(self, item: Any) -> None:
        self._queue.put_nowait(item)

    def close(self) -> None:
        subs = self._bus._subs.get(self.investigation_id)
        if subs is not None:
            subs.discard(self)
            if not subs:
                del self._bus._subs[self.investigation_id]

    def __aiter__(self) -> "Subscription":
        return self

    async def __anext__(self) -> Event | Ephemeral:
        item = await self._queue.get()
        if item is _CLOSED:
            self.close()
            raise StopAsyncIteration
        return item


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, set[Subscription]] = defaultdict(set)

    def publish(self, item: Event | Ephemeral) -> None:
        for sub in list(self._subs.get(item.investigation_id, ())):
            sub._put(item)

    def subscribe(self, investigation_id: str) -> Subscription:
        return Subscription(self, investigation_id)

    def end(self, investigation_id: str) -> None:
        """End every subscription to `investigation_id` (it was deleted)."""
        for sub in list(self._subs.get(investigation_id, ())):
            sub._put(_CLOSED)
