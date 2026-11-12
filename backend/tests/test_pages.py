import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from netgrip.adapters.fakes import FakeFetcher, FakeSearch
from netgrip.store.db import open_db
from netgrip.store.pages import PageStore, PageVersion, Unobtainable

URL = "https://example.org/a"


async def _noop(n, total, attempt):
    return None


class Clock:
    def __init__(self):
        self.t = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self):
        return self.t


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(db, tmp_path, clock):
    return PageStore(db, tmp_path / "data", now=clock)


def fetcher(**pages):
    return FakeFetcher({URL: {"text": "hello", "title": "T"}} | pages)


async def get(store, f, inv="i1", reuse="1d", url=URL):
    return await store.get_or_fetch(inv, url, reuse, f, _noop)


async def test_same_url_fetched_once_per_investigation(store):
    f = fetcher()
    a = await get(store, f, reuse="always_refetch")
    b = await get(store, f, reuse="always_refetch")
    assert a.id == b.id
    assert f.calls == [URL]


async def test_concurrent_requests_share_one_fetch(store):
    f = FakeFetcher({URL: {"text": "hello"}}, delay=0.05)
    results = await asyncio.gather(*(get(store, f) for _ in range(5)))
    assert f.calls == [URL]
    assert len({r.id for r in results}) == 1


async def test_fresh_page_reused_across_investigations(store, db):
    f = fetcher()
    a = await get(store, f, inv="i1")
    b = await get(store, f, inv="i2")
    assert a.id == b.id and f.calls == [URL]
    rows = await db.read("SELECT investigation_id FROM investigation_pages ORDER BY 1")
    assert [r[0] for r in rows] == ["i1", "i2"]


async def test_always_refetch_fetches_again_but_keeps_old_version(store, db):
    f = fetcher()
    a = await get(store, f, inv="i1")
    b = await get(store, f, inv="i2", reuse="always_refetch")
    assert a.id != b.id and f.calls == [URL, URL]
    assert (await db.read("SELECT COUNT(*) FROM page_versions"))[0][0] == 2
    assert await store.read_text(a.id) == "hello"
    latest = await db.read("SELECT latest_version_id FROM pages WHERE url = ?", (URL,))
    assert latest[0][0] == b.id


async def test_stale_page_refetched(store, clock):
    f = fetcher()
    a = await get(store, f, inv="i1")
    clock.t += timedelta(hours=25)
    b = await get(store, f, inv="i2")
    assert a.id != b.id and f.calls == [URL, URL]
    clock.t += timedelta(hours=1)
    c = await get(store, f, inv="i3")
    assert c.id == b.id


async def test_identical_bodies_stored_once_on_disk(store, tmp_path):
    f = FakeFetcher({URL: {"text": "same"}, "https://example.org/b": {"text": "same"}})
    a = await get(store, f)
    b = await get(store, f, url="https://example.org/b")
    assert isinstance(a, PageVersion) and a.id != b.id and a.raw_sha == b.raw_sha
    files = [p for p in (tmp_path / "data" / "pages").rglob("*") if p.is_file()]
    assert len(files) == 2  # one raw body, one text
    assert (tmp_path / "data" / "pages" / a.raw_sha[:2] / a.raw_sha).exists()


async def test_unobtainable_is_returned_not_raised(store):
    f = FakeFetcher({URL: {"unobtainable": True}})
    r = await get(store, f)
    assert isinstance(r, Unobtainable)
    assert [a.outcome for a in r.attempts] == ["blocked"] * 3
    assert isinstance(await get(store, f, url="https://unknown.example/"), Unobtainable)


async def test_scripted_attempts_and_scenario_fixtures():
    seen = []

    async def on_attempt(n, total, attempt):
        seen.append((n, total, attempt.outcome if attempt else None))

    f = FakeFetcher.from_scenario("great_wall_web")
    r = await f.fetch("https://example.org/history/wall-myth", on_attempt=on_attempt)
    assert r.status == "ok" and [a.route for a in r.attempts] == ["simple", "browser", "hardened"]
    assert seen[0] == (1, 3, None) and seen[-1] == (3, 3, "ok")
    hits = await FakeSearch.from_scenario("great_wall_web").search(
        "is it visible", max_results=1, exclude_domains=[], prefer="web"
    )
    assert len(hits) == 1
