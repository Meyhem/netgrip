"""System pauses (N-05, B4, S10): outages back off then pause, rejections pause at once, the
spending limit pauses at a step boundary and refuses resume until raised."""

import asyncio

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
    statuses,
)

from netgrip.boundary.commands import CommandRejected
from netgrip.engine.clock import FakeClock
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

    # The interrupted node is back to Pending while paused (node.reset outage).
    assert (await statuses(db))["n-1"] == "Pending"
    resets = [d for _, n, d in await events(db, "node.reset") if n == "n-1"]
    assert resets == [{"reason": "outage", "hint": None}]

    # In the morning: resume, nothing lost.
    client.queues["node.decide"] = [conclude()]
    client._last.pop("node.decide", None)
    await engine.submit(cmd("resume"))
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"
    assert len([n for _, n, _ in await events(db, "node.started") if n == "n-1"]) == 1
    assert (await statuses(db))["n-1"] == "Completed"


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


async def test_cap_reached_on_last_step_keeps_return_work_owed(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    async with db.tx() as tx:  # the conclusion (0.01) reaches the cap
        await tx.execute("UPDATE investigations SET spending_limit_usd = 0.01 WHERE id = ?", [INV])
    client = TrackingClient(BASE_SCRIPT)
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert (await pause_row(db))["pause_cause"] == "spending_limit"
    assert [c.purpose for c in client.calls] == ["node.decide"]  # no return check over the cap
    assert (await statuses(db))["n-1"] == "Completed"
    await engine.submit(cmd("raise_limit", spending_limit_usd=5.0))
    await engine.submit(cmd("resume"))
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"
    assert "node.relevance" in [c.purpose for c in client.calls]  # the return work ran


async def test_orchestrator_outage_backs_off_then_recovers(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    script = BASE_SCRIPT | {
        "node.relevance": [UNAVAILABLE, UNAVAILABLE, *BASE_SCRIPT["node.relevance"]]
    }
    engine = make_engine(db, tmp_path, TrackingClient(script))
    await run_to_end(engine)
    assert await state(db) == "Completed"
    assert engine.clock.sleeps == [1, 2]


async def test_orchestrator_outage_backs_off_then_pauses(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    engine = make_engine(
        db, tmp_path, TrackingClient(BASE_SCRIPT | {"orchestrator.next": [UNAVAILABLE]})
    )
    await run_to_end(engine)
    assert (await pause_row(db))["pause_cause"] == "model_unavailable"
    assert len(engine.clock.sleeps) > 2 and sum(engine.clock.sleeps) <= 300


async def test_backoff_restarts_after_the_step_advanced(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    decisions = [UNAVAILABLE, UNAVAILABLE, decide("search", query="wall"), UNAVAILABLE, conclude()]
    script = BASE_SCRIPT | {"node.decide": decisions}
    engine = make_engine(db, tmp_path, TrackingClient(script))
    await run_to_end(engine)
    assert await state(db) == "Completed"
    assert engine.clock.sleeps == [1, 2, 1]


class BlockingClock(FakeClock):
    """Every sleep blocks until cancelled: only a wake can end a backoff wait."""

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        await asyncio.Event().wait()


async def test_pause_cuts_backoff_wait_short(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [UNAVAILABLE]})
    engine = make_engine(db, tmp_path, client)
    engine.clock = BlockingClock()
    engine.start_runtime(INV)
    for _ in range(500):
        if engine.clock.sleeps:
            break
        await asyncio.sleep(0.001)
    await engine.submit(cmd("pause"))
    await asyncio.wait_for(engine.runtimes[INV].wait(), 2)
    row = await pause_row(db)
    assert row["state"] == "Paused" and row["pause_cause"] == "user"
    assert engine.clock.sleeps == [1]


async def test_recovered_outage_does_not_use_up_decisions(db, tmp_path):
    # Five unavailable answers, then the model is back: the node may still search (its
    # decision budget is sources + 3 = 5 usable decisions, none of them used yet).
    await seed(db, [("n-1", proposed("D1"))])
    decisions = [*[UNAVAILABLE] * 5, decide("search", query="wall"), conclude()]
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT | {"node.decide": decisions}))
    await run_to_end(engine)
    assert await state(db) == "Completed"
    assert engine.search.calls == ["wall"]
    routes = [d["route"] for _, n, d in await events(db, "node.step_completed")
              if n == "n-1" and d["kind"] == "decision"]  # fmt: skip
    assert routes == ["search", "conclude"]


async def test_spending_limit_stop_does_not_count_a_decision(db, tmp_path):
    # The cap stops the second decision before its call: only the first one is counted.
    engine, _ = await _capped(db, tmp_path)
    ctx = engine.runtimes[INV]._ctxs["n-1"]
    assert ctx.state.decisions == 1


REQUEST = {"raise": "request"}


async def test_refused_request_fails_the_node_instead_of_pausing(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [REQUEST]})  # refused every time
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert not [d for _, _, d in await events(db, "investigation.state_changed")
                if d["to"] == "Paused"]  # fmt: skip
    assert engine.clock.sleeps == []  # not treated as an outage
    failed = [d for _, n, d in await events(db, "node.failed") if n == "n-1"]
    assert failed and all("refused the request" in d["reason"] for d in failed)
    assert "fake: request rejected" in failed[0]["reason"]
    assert len(failed) == 2  # the one automatic retry was refused too
    assert (await statuses(db))["n-1"] == "Failed"
    assert await state(db) == "Completed"


async def test_refused_request_then_retry_succeeds(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.decide": [REQUEST, conclude()]})
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert [d["reason"] for _, _, d in await events(db, "node.reset")] == ["auto_retry"]
    assert (await statuses(db))["n-1"] == "Completed"
    assert await state(db) == "Completed"


async def test_refused_orchestrator_request_falls_back_without_pausing(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    client = TrackingClient(BASE_SCRIPT | {"node.relevance": [REQUEST]})
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert await state(db) == "Completed"
    assert [t for t, n, _ in await events(db) if n == "n-1" and t.startswith("node.relevance")
            ] == ["node.relevance_checked"]  # fmt: skip
    assert len([c for c in client.calls if c.purpose == "node.relevance"]) == 1
