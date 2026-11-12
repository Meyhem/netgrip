"""Shared limiters (D-05): one pool of model calls and one of searches for every runtime.

`async with limiter.model:` waits for a free place. `resize` takes effect at once: a larger
capacity wakes waiters, a smaller one lets the calls in flight finish.
"""

import asyncio


class Limiter:
    def __init__(self, name: str, capacity: int) -> None:
        self.name = name
        self.capacity = capacity
        self.in_use = 0
        self._waiters: list[asyncio.Future[None]] = []

    def resize(self, capacity: int) -> None:
        self.capacity = max(1, capacity)
        self._wake()

    def _wake(self) -> None:
        for f in self._waiters:
            if not f.done():
                f.set_result(None)
        self._waiters.clear()

    async def __aenter__(self) -> "Limiter":
        while self.in_use >= self.capacity:
            fut = asyncio.get_running_loop().create_future()
            self._waiters.append(fut)
            await fut
        self.in_use += 1
        return self

    async def __aexit__(self, *exc: object) -> None:
        self.in_use -= 1
        self._wake()


# Defaults match "Model calls at once 8" and "Searches at once 4"; Engine.start and the pools
# route resize them from the settings.
model = Limiter("model", 8)
search = Limiter("search", 4)


def resize_limiters(capacity) -> None:
    """From the `capacity` settings (model_calls, searches)."""
    model.resize(capacity.model_calls)
    search.resize(capacity.searches)
