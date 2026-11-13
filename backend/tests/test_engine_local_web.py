import asyncio
import os
import signal
from urllib.parse import urlsplit

import pytest
from great_wall_run import open_engine, run
from local_web import LocalSite, browsers_running, make_web

pytestmark = pytest.mark.browser


async def events(db, inv, type):
    rows = await db.read(
        "SELECT data FROM events WHERE investigation_id = ? AND type = ? ORDER BY seq", [inv, type]
    )
    import json

    return [json.loads(r["data"]) for r in rows]


async def open_web_engine(path, site, pages=2):
    web = make_web(path, site, pages)
    engine = await open_engine(path)
    engine.web = web
    engine.search, engine.fetcher = web.search, web.fetcher
    engine.apply_settings(
        await __import__("netgrip.store.settings", fromlist=["x"]).get_settings(engine.db)
    )
    await web.start()
    return engine, web


async def close(engine):
    await engine.stop()
    await engine.db.close()


async def test_investigation_completes_against_local_site(tmp_path):
    site = await LocalSite().start()
    engine, web = await open_web_engine(tmp_path, site)
    try:
        r = run(engine)
        await r.approved()
        await r.finished(timeout=120)
        db = engine.db
        state = (await db.read("SELECT state FROM investigations WHERE id = ?", [r.inv]))[0]
        assert state["state"] == "Completed"
        failed = await db.read(
            "SELECT id FROM nodes WHERE investigation_id = ? AND status = 'Failed'", [r.inv]
        )
        assert failed == []  # E5: page trouble never fails a node
        gone = {d["url"]: d["attempts"] for d in await events(db, r.inv, "page.unobtainable")}
        assert site.url("/hang1") in gone and all(
            a["outcome"] in ("timeout", "error") for a in gone[site.url("/hang1")]
        )
        assert len(gone[site.url("/hang1")]) >= 4  # retried on every route before giving up
        assert site.url("/forbidden") in gone
        assert site.url("/js") not in gone  # the JavaScript page was obtained by the browser
        pages = await db.read("SELECT url FROM page_versions")
        assert site.url("/js") in {p["url"] for p in pages}
        retries = [
            d for d in await events(db, r.inv, "node.activity") if d.get("activity") == "Retrying"
        ]
        assert retries  # the node showed "Retrying n of m"
    finally:
        await close(engine)
        await site.stop()
    assert browsers_running(tmp_path) == []


async def test_two_investigations_share_the_pool(tmp_path):
    site = await LocalSite().start()
    engine, web = await open_web_engine(tmp_path, site, pages=2)
    try:
        a, b = run(engine), run(engine)
        await a.approved()
        await b.approved()
        await asyncio.gather(a.finished(timeout=180), b.finished(timeout=180))
        for r in (a, b):
            row = (await engine.db.read("SELECT state FROM investigations WHERE id = ?", [r.inv]))[
                0
            ]
            assert row["state"] == "Completed"
        assert web.pool.peak_open_pages + 0 <= 2
        assert web.slots.in_use == 0
    finally:
        await close(engine)
        await site.stop()


async def test_killed_run_is_swept_and_resumed_without_refetching(tmp_path):
    site = await LocalSite().start()
    engine, web = await open_web_engine(tmp_path, site)
    r = run(engine)
    await r.approved()

    async def until(cond):
        for _ in range(1200):
            if await cond():
                return
            await asyncio.sleep(0.02)
        raise AssertionError("the run never got there")

    async def stored_one():
        return (await engine.db.read("SELECT COUNT(*) AS n FROM page_versions"))[0]["n"] >= 1

    async def browser_busy():
        return bool(web.pool.open_pages or web.hardened.open_pages)

    await until(stored_one)
    await until(browser_busy)  # a page is being fetched in a browser right now
    assert web.pool.open_pages or web.hardened.open_pages
    # A crash: the runtimes and the database vanish, the browsers keep running.
    stored = {x["url"] for x in await engine.db.read("SELECT url FROM page_versions")}
    old = web.pool.pids + web.hardened.pids

    async def nothing(*a, **k):  # a dead process cleans nothing up
        return None

    for pool in (web.pool, web.hardened):
        pool._close_session = pool._destroy = nothing
    for rt in list(engine.runtimes.values()):
        await rt.stop(abandon=True)
    web.pool._watchdog.cancel()
    await engine.db.close()
    assert old and browsers_running(tmp_path)
    before = {urlsplit(u).path: site.hits[urlsplit(u).path] for u in stored}

    engine2, web2 = await open_web_engine(tmp_path, site)
    try:
        for pid in old:
            assert (
                not os.path.exists(f"/proc/{pid}")
                or open(f"/proc/{pid}/stat").read().split()[2] == "Z"
            )
        await asyncio.wait_for(engine2.runtimes[r.inv].wait(), 180)
        row = (await engine2.db.read("SELECT state FROM investigations WHERE id = ?", [r.inv]))[0]
        assert row["state"] == "Completed"
        for u in stored:
            path = urlsplit(u).path
            assert site.hits[path] == before[path]  # cached pages were not fetched again
    finally:
        await close(engine2)
        await site.stop()
        await web.pool._pw.stop()
        for pid in old:
            try:
                os.killpg(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
