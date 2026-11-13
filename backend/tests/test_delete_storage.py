"""Deleting an investigation and reporting disk use (Phase 8, Task 5)."""

import asyncio
from pathlib import Path

import pytest
from great_wall_run import NASA, GatedFetcher, open_engine, run

from netgrip.adapters.fakes import FakeModelClient
from netgrip.boundary.commands import CommandRejected
from netgrip.store.projections import ID_COLUMNS, STATE_TABLES

OTHER = ["extractions", "reconciled_claims", "investigation_pages", "events", "commands"]


async def count(db, table, inv) -> int:
    col = ID_COLUMNS.get(table, "investigation_id")
    return (await db.read(f"SELECT COUNT(*) FROM {table} WHERE {col} = ?", [inv]))[0][0]


async def everything_of(db, inv) -> dict[str, int]:
    return {t: await count(db, t, inv) for t in [*STATE_TABLES, *OTHER]}


def page_files(engine) -> list[Path]:
    return [p for p in (engine.config.data_dir / "pages").rglob("*") if p.is_file()]


def two_runs():
    """Each investigation is served the whole script from the start (as in fake mode)."""
    return FakeModelClient.from_scenario("great_wall", repeat_last=True, per_investigation=True)


async def finished_run(engine):
    r = run(engine)
    await r.approved()
    await r.finished()
    return r.inv


async def test_delete_running_investigation_stops_it_first(tmp_path):
    gate, entered = asyncio.Event(), asyncio.Event()

    async def hold():
        entered.set()
        await gate.wait()

    engine = await open_engine(tmp_path, fetcher=GatedFetcher(NASA, hold))
    try:
        r = run(engine)
        await r.approved()
        await asyncio.wait_for(entered.wait(), 10)  # a step is in flight
        await engine.delete_investigation(r.inv)
        assert r.inv not in engine.runtimes
        gate.set()  # the held fetch would now go on and write
        await asyncio.sleep(0.3)
        assert all(n == 0 for n in (await everything_of(engine.db, r.inv)).values())
        assert (await engine.db.read("SELECT COUNT(*) FROM events"))[0][0] == 0
    finally:
        gate.set()
        await engine.stop()
        await engine.db.close()


async def test_delete_removes_events_state_evidence_report(tmp_path):
    engine = await open_engine(tmp_path)
    try:
        inv = await finished_run(engine)
        before = await everything_of(engine.db, inv)
        assert before["events"] and before["claims"] and before["reports"] and before["sources"]
        freed = await engine.delete_investigation(inv)
        assert freed > 0
        assert all(n == 0 for n in (await everything_of(engine.db, inv)).values())
        assert (
            page_files(engine) == [] and (await engine.db.read("SELECT 1 FROM page_versions")) == []
        )
    finally:
        await engine.stop()
        await engine.db.close()


async def test_shared_page_survives_first_delete_and_goes_with_second(tmp_path):
    engine = await open_engine(tmp_path, model=two_runs())
    try:
        first, second = await finished_run(engine), await finished_run(engine)
        shared = {r["page_version_id"] for r in await engine.db.read(
            "SELECT page_version_id FROM investigation_pages WHERE investigation_id = ?", [first]
        )} & {r["page_version_id"] for r in await engine.db.read(
            "SELECT page_version_id FROM investigation_pages WHERE investigation_id = ?", [second]
        )}  # fmt: skip
        assert shared, "the second run reused the first run's pages (V9)"
        files = page_files(engine)
        size = sum(f.stat().st_size for f in files)
        await engine.delete_investigation(first)
        assert page_files(engine) == files  # still used by the second
        assert {r["id"] for r in await engine.db.read("SELECT id FROM page_versions")} >= shared
        assert (await engine.pages.read_text(next(iter(shared)))) != ""
        freed = await engine.delete_investigation(second)
        assert page_files(engine) == [] and freed >= size
        assert (await engine.db.read("SELECT COUNT(*) FROM pages"))[0][0] == 0
    finally:
        await engine.stop()
        await engine.db.close()


async def test_disk_usage_counts_shared_page_for_both(tmp_path):
    engine = await open_engine(tmp_path, model=two_runs())
    try:
        first, second = await finished_run(engine), await finished_run(engine)
        a, b = await engine.usage.of(first), await engine.usage.of(second)
        pages = sum(f.stat().st_size for f in page_files(engine))
        assert pages > 0 and a > pages and b > pages  # each counts every page it uses
        assert (
            a + b > pages + (await engine.usage.rows(first)) + (await engine.usage.rows(second)) - 1
        )
    finally:
        await engine.stop()
        await engine.db.close()


async def test_disk_usage_is_cached_until_the_log_moves(tmp_path):
    engine = await open_engine(tmp_path)
    try:
        inv = await finished_run(engine)
        first = await engine.usage.of(inv)
        assert await engine.usage.of(inv) == first
        async with engine.db.tx() as tx:
            await tx.execute(
                "UPDATE investigations SET last_seq = last_seq + 1 WHERE id = ?", [inv]
            )
            await tx.execute(
                "INSERT INTO instructions(id, investigation_id, text, state, queued_seq)"
                " VALUES ('x', ?, ?, 'queued', 1)",
                [inv, "z" * 5000],
            )
        assert await engine.usage.of(inv) >= first + 5000
    finally:
        await engine.stop()
        await engine.db.close()


async def test_storage_total_is_on_disk_size(app_client):
    inv = "11111111-1111-4111-8111-111111111111"
    await app_client.post("/api/investigations", json={"id": inv, "prompt": "p"})
    data_dir = app_client.app.state.config.data_dir
    storage = (await app_client.get("/api/system/storage")).json()
    on_disk = sum(f.stat().st_size for f in data_dir.rglob("*") if f.is_file())
    assert storage["total_bytes"] == on_disk and storage["investigations"] == 1
    row = (await app_client.get("/api/investigations")).json()[0]
    assert row["disk_bytes"] > 0
    snap = (await app_client.get(f"/api/investigations/{inv}")).json()
    assert snap["investigation"]["disk_bytes"] == row["disk_bytes"]


async def test_delete_unknown_is_404(app_client):
    r = await app_client.delete("/api/investigations/22222222-2222-4222-8222-222222222222")
    assert r.status_code == 404


async def test_delete_unknown_raises_not_found(tmp_path):
    engine = await open_engine(tmp_path)
    try:
        with pytest.raises(CommandRejected):
            await engine.delete_investigation("nope")
    finally:
        await engine.stop()
        await engine.db.close()
