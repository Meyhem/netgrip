"""The fake Great Wall run end to end, shared by the scenario tests and the golden contract:
the planning script and the scripted web of NETGRIP_FAKE=1, from draft to Completed."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from netgrip.adapters.fakes import FakeFetcher, FakeModelClient, FakeSearch
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command
from netgrip.config import Config
from netgrip.engine.clock import FakeClock
from netgrip.engine.engine import Engine
from netgrip.store.db import open_db
from netgrip.store.settings import patch_settings

PROMPT = "Is the Great Wall visible from space?"
NASA = "https://example.org/nasa/great-wall-from-orbit"
MYTH = "https://example.org/history/wall-myth"


class GatedFetcher(FakeFetcher):
    """The scenario's pages; the first fetch of `url` first awaits `on_fetch()` (the run is
    held inside the read step while it runs)."""

    def __init__(
        self, url: str | None = None, on_fetch: Callable[[], Awaitable[None]] | None = None
    ):
        base = FakeFetcher.from_scenario("great_wall_web")
        super().__init__(base.fixtures)
        self.url, self.on_fetch = url, on_fetch

    async def fetch(self, url, *, on_attempt):
        if url == self.url and self.on_fetch is not None:
            hook, self.on_fetch = self.on_fetch, None
            await hook()
        return await super().fetch(url, on_attempt=on_attempt)


async def open_engine(
    path: Path,
    *,
    model: FakeModelClient | None = None,
    fetcher: FakeFetcher | None = None,
    parallel: int | None = None,
) -> Engine:
    path.mkdir(parents=True, exist_ok=True)
    db = await open_db(path / "netgrip.sqlite")
    if parallel is not None:
        await patch_settings(db, {"effort": {"Medium": {"parallel": parallel}}})
    engine = Engine(
        db,
        Config(data_dir=path, fake=True),
        EventBus(),
        model or FakeModelClient.from_scenario("great_wall", repeat_last=True),
        search=FakeSearch.from_scenario("great_wall_web"),
        fetcher=fetcher or GatedFetcher(),
        clock=FakeClock(),
    )
    await engine.start()
    return engine


class Run:
    def __init__(self, engine: Engine, inv: str, command_ids: Callable[[], uuid.UUID]) -> None:
        self.engine, self.inv, self._ids = engine, inv, command_ids

    async def submit(self, type: str, **payload) -> None:
        cmd = Command(id=self._ids(), type=type, investigation_id=self.inv, payload=payload)
        await self.engine.submit(cmd)
        await self.engine.planning.idle(self.inv)

    async def approved(self) -> None:
        """Create, draft and approve the plan; the runtime is started, not awaited."""
        await self.engine.create_investigation(uuid.UUID(self.inv), PROMPT, {})
        await self.submit("draft_plan")
        await self.submit("approve_plan")

    async def finished(self, timeout: float = 20) -> None:
        await asyncio.wait_for(self.engine.runtimes[self.inv].wait(), timeout)


def run(engine: Engine, inv: str | None = None, command_ids=uuid.uuid4) -> Run:
    return Run(engine, inv or str(uuid.uuid4()), command_ids)
