"""Focus, go deeper, re-run and finish now (domain 4.9, B2, S5, S8)."""

import asyncio
import json
import uuid

import pytest
from test_runtime import (
    BASE_SCRIPT,
    INV,
    TrackingClient,
    cmd,
    conclude,
    decide,
    ev,
    events,
    make_engine,
    proposed,
    seed,
    state,
    statuses,
)

from netgrip.boundary.commands import Command, CommandRejected
from netgrip.engine.orchestrator import synthesis_claims
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def ncmd(type, node_id=None, **payload):
    return Command(
        id=uuid.uuid4(), type=type, investigation_id=INV, node_id=node_id, payload=payload
    )


async def until(check):
    for _ in range(300):
        if await check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def finish_node(db, nid, claim=None):
    drafts = [
        ev("node.started", {"attempt": 1, "brief": {}}, node_id=nid, actor="node"),
        ev("node.completed", {"verdict": {"text": "v", "confidence": "high"},
                              "open_questions": [], "off_topic": False}, node_id=nid,
           actor="node"),
    ]  # fmt: skip
    if claim:
        data = {"claim_id": f"c-{nid}", "text": claim, "status": "Supported",
                "supporting": [], "contradicting": []}  # fmt: skip
        drafts.append(ev("claim.added", data, node_id=nid, actor="node"))
    await append_and_project(db, INV, drafts)


async def test_focus_runs_only_branch_and_reasons_say_so(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2")), ("n-3", proposed("D3"))])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("run_only_branch", "n-2"))
    engine.start_runtime(INV)

    async def done():
        return (await statuses(db))["n-2"] == "Completed"

    await until(done)
    await asyncio.sleep(0.05)
    st = await statuses(db)
    assert st["n-1"] == st["n-3"] == "Pending"
    reasons = (await events(db, "schedule.updated"))[0][2]["reasons"]
    assert reasons == {"n-1": "focus:n-2", "n-3": "focus:n-2"}
    assert await state(db) == "Running"  # not finished: the user runs only a branch
    snap = (await db.read("SELECT focus_node_id FROM investigations"))[0]
    assert snap["focus_node_id"] == "n-2"
    await engine.runtimes[INV].stop()


async def test_run_everything_resumes_rest(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("run_only_branch", "n-2"))
    engine.start_runtime(INV)

    async def done():
        return (await statuses(db))["n-2"] == "Completed"

    await until(done)
    await engine.submit(cmd("run_everything"))
    await engine.runtimes[INV].wait()
    st = await statuses(db)
    assert st["n-1"] == st["n-2"] == "Completed"
    assert await state(db) == "Completed"
    assert (await db.read("SELECT focus_node_id FROM investigations"))[0][0] is None


async def test_focus_finishes_step_outside_then_returns_it_to_pending(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    gate = asyncio.Event()
    script = {**BASE_SCRIPT, "node.decide:n-1": [decide("search", query="q"), conclude()]}
    client = TrackingClient(script, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(ncmd("run_only_branch", "n-2"))
    gate.set()

    async def settled():
        return (await statuses(db))["n-2"] == "Completed" and not engine.runtimes[INV]._tasks

    await until(settled)
    st = await statuses(db)
    assert st["n-1"] == "Pending"
    assert [(n, d["reason"]) for _, n, d in await events(db, "node.reset")] == [("n-1", "focus")]
    await engine.runtimes[INV].stop()


async def test_go_deeper_raises_branch_budget_and_allows_more_children(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    await append_and_project(db, INV, [
        ev("node.proposed", proposed("D1a", parent="n-1", depth=2), node_id="n-1a"),
        ev("node.approved", {"budget": {"sources": 4, "child_nodes": 0}}, node_id="n-1a"),
    ])  # fmt: skip
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    before = (await db.read("SELECT nodes_extra FROM investigations"))[0][0]
    await engine.submit(ncmd("go_deeper", "n-1"))
    [(_, node, data)] = await events(db, "node.budget_changed")
    assert node == "n-1" and data["cause"] == "go_deeper"
    # D1 had {sources 2, child_nodes 2}: 1.5x rounded up, one level deeper.
    assert data["budget"]["n-1"] == {"sources": 3, "child_nodes": 3, "depth_extra": 1}
    assert data["budget"]["n-1a"]["sources"] == 6
    assert "n-2" not in data["budget"]  # only the branch
    rows = {r["id"]: json.loads(r["budget"]) for r in await db.read("SELECT id, budget FROM nodes")}
    assert rows["n-1"]["child_nodes"] == 3 and rows["n-2"]["child_nodes"] == 2
    # The investigation ceiling rises by the child nodes added (1 for D1, more for D1a).
    after = (await db.read("SELECT nodes_extra FROM investigations"))[0][0]
    assert after - before == (3 - 2) + (rows["n-1a"]["child_nodes"] - 0)
    assert rows["n-1a"]["child_nodes"] > 0  # a node at the deepest level may now have children


async def test_rerun_resets_node_reuses_pages_and_extractions(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    await finish_node(db, "n-1", claim="The Wall is long")
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    assert [c.id for c in await synthesis_claims(db, INV)] == ["c-n-1"]
    await engine.submit(ncmd("rerun_node", "n-1"))
    row = (await db.read("SELECT status, verdict FROM nodes WHERE id = 'n-1'"))[0]
    assert row["status"] == "Pending" and row["verdict"] is None
    [(_, _, w)] = await events(db, "claim.withdrawn")
    assert w == {"claim_ids": ["c-n-1"], "cause": "rerun"}
    assert await synthesis_claims(db, INV) == []  # withdrawn claims are not used
    assert len(await db.read("SELECT id FROM claims")) == 1  # but stay stored
    [(_, _, reset)] = await events(db, "node.reset")
    assert reset["reason"] == "rerun"
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()
    assert (await statuses(db))["n-1"] == "Completed"
    assert len(await events(db, "node.started")) == 3  # n-1 again, n-2
    assert await state(db) == "Completed"


async def test_rerun_refused_for_running_node(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    gate = asyncio.Event()
    client = TrackingClient(BASE_SCRIPT, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    with pytest.raises(CommandRejected) as e:
        await engine.submit(ncmd("rerun_node", "n-1"))
    assert e.value.code == "wrong_state"
    gate.set()
    await engine.runtimes[INV].wait()


async def test_finish_now_goes_to_synthesising_and_marks_ended_early(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2", depends_on=["n-1"]))])
    gate = asyncio.Event()
    client = TrackingClient(BASE_SCRIPT, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(cmd("finish_now"))
    assert await state(db) == "Running"  # the step in flight finishes first
    gate.set()
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"
    [(_, _, report)] = await events(db, "report.created")
    assert report["ended_early"] is True
    [(_, _, concluding)] = await events(db, "investigation.concluding")
    assert concluding["ended_early"] is True
    assert (await statuses(db))["n-2"] == "Pending"  # never started
    states = [d["to"] for _, _, d in await events(db, "investigation.state_changed")][-2:]
    assert states == ["Synthesising", "Completed"]


async def test_finish_now_from_paused_synthesises_at_once(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    await append_and_project(db, INV, [
        ev("investigation.state_changed", {"from": "Running", "to": "Paused", "origin": "user",
                                           "cause": "user", "detail": None}, actor="user"),
    ])  # fmt: skip
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(cmd("finish_now"))
    await until(lambda: _completed(db))
    [(_, _, report)] = await events(db, "report.created")
    assert report["ended_early"] is True


async def _completed(db):
    return await state(db) == "Completed"


async def test_finish_now_refused_when_not_running_paused_or_stopped(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    await append_and_project(db, INV, [
        ev("investigation.state_changed", {"from": "Running", "to": "Synthesising",
                                           "origin": "orchestrator"}),
    ])  # fmt: skip
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    with pytest.raises(CommandRejected) as e:
        await engine.submit(cmd("finish_now"))
    assert e.value.code == "wrong_state"
