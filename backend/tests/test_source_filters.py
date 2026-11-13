import json
import uuid

from great_wall_run import PROMPT, GatedFetcher, open_engine, run

from netgrip.adapters.fakes import FakeSearch
from netgrip.adapters.search import SearchRejected
from netgrip.engine import limiter
from netgrip.engine.engine import Engine
from netgrip.store.settings import get_settings, patch_settings


class IgnoresFilterSearch(FakeSearch):
    """A provider that ignores `exclude_domains`: the engine must enforce it again."""

    async def search(self, query, *, max_results, exclude_domains, prefer):
        self.last = (exclude_domains, prefer)
        return await super().search(
            query, max_results=max_results, exclude_domains=[], prefer=prefer
        )


async def start(tmp_path, settings, search=None):
    fetcher = GatedFetcher()
    engine = await open_engine(tmp_path, fetcher=fetcher)
    if search is not None:
        engine.search = search
    r = run(engine)
    await engine.create_investigation(uuid.UUID(r.inv), PROMPT, settings)
    await r.submit("draft_plan")
    await r.submit("approve_plan")
    await r.finished()
    return engine, r, fetcher


async def test_excluded_domain_never_fetched(tmp_path):
    search = IgnoresFilterSearch.from_scenario("great_wall_web")
    engine, r, fetcher = await start(tmp_path, {"excluded_domains": ["example.org"]}, search)
    control, _, control_fetcher = await start(
        tmp_path / "control", {}, IgnoresFilterSearch.from_scenario("great_wall_web")
    )
    try:
        assert control_fetcher.calls  # without the filter the pages are fetched
        assert search.last[0] == ["example.org"]  # sent to the provider
        assert fetcher.calls == []  # and enforced again before any fetch
        rows = await engine.db.read(
            "SELECT 1 FROM events WHERE investigation_id = ? AND type = 'page.unobtainable'",
            [r.inv],
        )
        assert rows == []  # a skipped source is not an unobtainable one (W4)
    finally:
        await control.stop()
        await control.db.close()
        await engine.stop()
        await engine.db.close()


async def test_excluded_domains_recorded_for_report_limits(tmp_path):
    engine, r, _ = await start(tmp_path, {"excluded_domains": ["example.org", "reddit.com"]})
    try:
        row = (await engine.db.read("SELECT settings FROM investigations WHERE id = ?", [r.inv]))[0]
        assert json.loads(row["settings"])["excluded_domains"] == ["example.org", "reddit.com"]
    finally:
        await engine.stop()
        await engine.db.close()


async def test_primary_preference_reaches_search_and_prompt(tmp_path):
    search = IgnoresFilterSearch.from_scenario("great_wall_web")
    engine, r, _ = await start(tmp_path, {"prefer": "primary"}, search)
    try:
        assert search.last[1] == "primary"
        decisions = [c for c in engine.model_client.calls if c.purpose == "node.decide"]
        assert decisions and any(
            "primary sources only" in m.content for c in decisions for m in c.messages if m.content
        )
    finally:
        await engine.stop()
        await engine.db.close()


async def test_refused_query_is_a_search_with_no_results(tmp_path):
    class Refusing(FakeSearch):
        async def search(self, query, **kw):
            raise SearchRejected("request", "that query was refused")

    engine, r, fetcher = await start(tmp_path, {}, Refusing({}))
    try:
        state = (await engine.db.read("SELECT state FROM investigations WHERE id = ?", [r.inv]))[0]
        assert state["state"] != "Paused" and fetcher.calls == []
    finally:
        await engine.stop()
        await engine.db.close()


async def test_capacity_change_resizes_pool(app_client):
    engine: Engine = app_client.app.state.engine

    class W:
        def __init__(self):
            self.seen = None

        def apply(self, cap, politeness):
            self.seen = (cap.browser_pages, politeness)

        def health(self):
            raise AssertionError

    engine.web = web = W()
    r = await app_client.patch(
        "/api/settings",
        json={"capacity": {"browser_pages": 3, "model_calls": 5}, "politeness_seconds": 4},
    )
    assert r.status_code == 200
    assert web.seen == (3, 4)
    assert limiter.model.capacity == 5
    await patch_settings(engine.db, {"capacity": {"model_calls": 8}})
    engine.apply_settings(await get_settings(engine.db))
    engine.web = None


async def test_pools_endpoint_reports_health(app_client):
    from netgrip.adapters.browser_pool import PoolHealth

    class W:
        def apply(self, cap, politeness): ...

        def health(self):
            return PoolHealth(4, 1, 2, 7)

    engine: Engine = app_client.app.state.engine
    engine.web = W()
    try:
        b = (await app_client.get("/api/system/pools")).json()["browsers"]
        assert b == {"in_use": 4, "limit": 6, "open": 1, "restarts_today": 2, "timed_out_today": 7}
    finally:
        engine.web = None
