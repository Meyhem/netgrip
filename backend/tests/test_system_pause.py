"""System pauses (N-05, B4, S10): outages back off then pause, rejections pause at once, the
spending limit pauses at a step boundary and refuses resume until raised."""

import pytest
from test_runtime import (
    BASE_SCRIPT,
    INV,
    TrackingClient,
    cmd,
    conclude,
    decide,
    events,
    make_engine,
    proposed,
    seed,
    state,
)

from netgrip.boundary.commands import CommandRejected
from netgrip.store.db import open_db
from netgrip.store.settings import key_status, set_key

UNAVAILABLE = {"raise": "unavailable"}


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


async def run_to_end(engine):
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()


def decides(client):
    return [c for c in client.calls if c.purpose == "node.decide"]


async def pause_row(db):
    rows = await db.read(
        "SELECT state, pause_cause, pause_detail FROM investigations WHERE id = ?", [INV]
    )
    return dict(rows[0])


async def last_pause(db):
    return [d for _, _, d in await events(db, "investigation.state_changed")][-1]


async def test_outage_backs_off_then_pauses_with_reason(db, tmp_path):
    # S10: the model stops answering overnight.
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [UNAVAILABLE]})
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)

    row = await pause_row(db)
    assert row["state"] == "Paused" and row["pause_cause"] == "model_unavailable"
    change = await last_pause(db)
    assert change["origin"] == "system" and change["cause"] == "model_unavailable"
    sleeps = engine.clock.sleeps
    assert sleeps[:6] == [1, 2, 4, 8, 16, 30] and max(sleeps) == 30
    assert sum(sleeps) <= 300
    retries = [d for t, n, d in await events(db, "node.activity") if d["activity"] == "Retrying"]
    assert len(retries) == len(sleeps)
    assert [r["retry"]["n"] for r in retries] == list(range(1, len(sleeps) + 1))
    assert {r["retry"]["m"] for r in retries} == {len(sleeps)}
    # One call per attempt, none after the pause.
    calls_at_pause = len(client.calls)
    assert len(decides(client)) == len(sleeps) + 1
    assert calls_at_pause == len(client.calls)

    # In the morning: resume, nothing lost.
    client.queues["node.decide"] = [conclude()]
    client._last.pop("node.decide", None)
    await engine.submit(cmd("resume"))
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"


async def test_outage_that_recovers_does_not_pause(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [UNAVAILABLE, UNAVAILABLE, conclude()]})
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert await state(db) == "Completed"
    assert engine.clock.sleeps == [1, 2]
    assert not [d for _, _, d in await events(db, "investigation.state_changed")
                if d["to"] == "Paused"]  # fmt: skip


async def test_search_outage_pauses_with_search_cause(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [decide("search", query="wall")]})
    engine = make_engine(db, tmp_path, client)
    engine.search.fixtures = {"results": [{"match": "wall", "raise": "unavailable"}]}
    await run_to_end(engine)
    assert (await pause_row(db))["pause_cause"] == "search_unavailable"
    assert sum(engine.clock.sleeps) <= 300


async def test_rejected_key_pauses_immediately_without_retry(db, tmp_path):
    await set_key(db, "model", "sk-test")
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [{"raise": "key"}]})
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    row = await pause_row(db)
    assert row["state"] == "Paused" and row["pause_cause"] == "key_rejected"
    assert (await last_pause(db))["origin"] == "system"
    assert engine.clock.sleeps == []
    assert len(decides(client)) == 1
    status = await key_status(db, "model")
    assert status.status == "rejected" and "fake: key rejected" in status.message


async def test_rejected_search_key_marks_search_key(db, tmp_path):
    await set_key(db, "search", "tv-test")
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [decide("search", query="wall")]})
    engine = make_engine(db, tmp_path, client)
    engine.search.fixtures = {"results": [{"match": "wall", "raise": "key"}]}
    await run_to_end(engine)
    assert (await pause_row(db))["pause_cause"] == "key_rejected"
    assert engine.clock.sleeps == []
    assert (await key_status(db, "search")).status == "rejected"


async def test_credit_exhausted_pauses_immediately(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [{"raise": "credit"}]})
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert (await pause_row(db))["pause_cause"] == "credit_exhausted"
    assert engine.clock.sleeps == []
    assert len(decides(client)) == 1


async def _capped(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    async with db.tx() as tx:  # each fake call costs 0.01
        await tx.execute("UPDATE investigations SET spending_limit_usd = 0.01 WHERE id = ?", [INV])
    client = TrackingClient(
        BASE_SCRIPT | {"node.decide": [decide("search", query="wall"), conclude()]}
    )
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    return engine, client


async def test_cap_reached_mid_node_commits_step_then_pauses(db, tmp_path):
    engine, client = await _capped(db, tmp_path)
    row = await pause_row(db)
    assert row["state"] == "Paused" and row["pause_cause"] == "spending_limit"
    assert (await last_pause(db))["origin"] == "system"
    assert len(client.calls) == 1  # the first decision only; no further model call
    evs = [(t, n) for t, n, _ in await events(db)]
    spend = evs.index(("spend.recorded", "n-1"))
    committed = evs.index(("node.step_completed", "n-1"))
    paused = max(i for i, (t, _) in enumerate(evs) if t == "investigation.state_changed")
    assert spend < paused and committed < paused
    spent = (await db.read("SELECT spent_usd FROM investigations WHERE id = ?", [INV]))[0][0]
    assert spent == pytest.approx(0.01)


async def test_resume_refused_while_cap_still_reached(db, tmp_path):
    engine, client = await _capped(db, tmp_path)
    with pytest.raises(CommandRejected) as e:
        await engine.submit(cmd("resume"))
    assert e.value.code == "limit_reached"
    assert await state(db) == "Paused"
    assert len(client.calls) == 1


async def test_raise_limit_then_resume_continues(db, tmp_path):
    engine, client = await _capped(db, tmp_path)
    await engine.submit(cmd("raise_limit", spending_limit_usd=5.0))
    assert await state(db) == "Paused"  # raising does not resume by itself
    await engine.submit(cmd("resume"))
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"
    assert len(decides(client)) == 2


async def test_resume_during_enter_paused_is_not_lost(db, tmp_path):
    """A resume that commits while the pause write waits for the writer must win."""
    await seed(db, [("n-1", proposed("D1"))])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    rt = engine.start_runtime(INV)
    await rt.wait()  # completed; reuse the object to exercise _enter_paused directly
    async with db.tx() as tx:
        await tx.execute("UPDATE investigations SET state = 'Running' WHERE id = ?", [INV])
    real_tx = db.tx

    def racing_tx():
        rt.resume()  # the resume handler's after_commit runs before our tx gets the lock
        db.tx = real_tx
        return real_tx()

    rt.request_pause("user", None, "user")
    pause = rt._pause
    db.tx = racing_tx
    try:
        await rt._enter_paused(pause)
    finally:
        db.tx = real_tx
        await rt.stop(abandon=True)
    assert await state(db) == "Running"
