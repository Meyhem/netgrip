"""Ignore, restore, pause and resume a branch (domain 4.9, S3, U3, P9)."""

import asyncio
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


def ncmd(type, node_id, **payload):
    return Command(
        id=uuid.uuid4(), type=type, investigation_id=INV, node_id=node_id, payload=payload
    )


async def add_claim(db, node_id, text="The Wall is long"):
    await append_and_project(db, INV, [
        ev("claim.added", {"claim_id": f"c-{node_id}", "text": text, "status": "Supported",
                           "supporting": [], "contradicting": []}, node_id=node_id, actor="node"),
    ])  # fmt: skip


async def inclusion(db):
    rows = await db.read("SELECT id, inclusion FROM nodes WHERE investigation_id = ?", [INV])
    return {r["id"]: r["inclusion"] for r in rows}


async def seed_tree(db):
    """R with D1 (children D1a, D1b) and D2; D1's children are approved too."""
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    await append_and_project(db, INV, [
        ev("node.proposed", proposed("D1a", parent="n-1", depth=2), node_id="n-1a"),
        ev("node.proposed", proposed("D1b", parent="n-1", depth=2), node_id="n-1b"),
        ev("node.approved", {"budget": {"sources": 2, "child_nodes": 0}}, node_id="n-1a"),
        ev("node.approved", {"budget": {"sources": 2, "child_nodes": 0}}, node_id="n-1b"),
    ])  # fmt: skip


async def test_ignore_stops_branch_and_excludes_claims(db, tmp_path):
    await seed_tree(db)
    await add_claim(db, "n-1a")
    await add_claim(db, "n-2")
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    assert len(await synthesis_claims(db, INV)) == 2
    await engine.submit(ncmd("ignore_branch", "n-1"))
    assert set((await inclusion(db)).values()) == {"Included", "Ignored"}
    assert (await inclusion(db))["n-1a"] == "Ignored"
    # Their claims leave synthesis and the briefs, and stay stored.
    assert [c.id for c in await synthesis_claims(db, INV)] == ["c-n-2"]
    assert len(await db.read("SELECT id FROM claims")) == 2
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()
    st = await statuses(db)
    assert st["n-2"] == "Completed"
    assert st["n-1"] == st["n-1a"] == st["n-1b"] == "Pending"  # never started
    assert await state(db) == "Completed"


async def test_ignore_mid_step_finishes_step_then_stops(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    gate = asyncio.Event()
    script = {**BASE_SCRIPT, "node.decide:n-1": [decide("search", query="q"), conclude()]}
    client = TrackingClient(script, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(ncmd("ignore_branch", "n-1"))
    gate.set()
    await engine.runtimes[INV].wait()
    n1_calls = [c for c in client.calls if c.purpose == "node.decide" and c.node_ref == "n-1"]
    assert len(n1_calls) == 1  # the step in flight finished; nothing after it
    steps = [t for t, n, _ in await events(db) if n == "n-1" and t == "node.step_completed"]
    assert len(steps) == 1  # and it committed
    resets = await events(db, "node.reset")
    assert [(n, d["reason"]) for _, n, d in resets] == [("n-1", "ignored")]
    st = await statuses(db)
    assert st["n-1"] == "Pending" and st["n-2"] == "Completed"
    assert await state(db) == "Completed"


async def test_restore_brings_back_results_without_rerun(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    await append_and_project(db, INV, [
        ev("node.started", {"attempt": 1, "brief": {}}, node_id="n-1", actor="node"),
        ev("node.completed", {"verdict": {"text": "v", "confidence": "high"},
                              "open_questions": [], "off_topic": False}, node_id="n-1",
           actor="node"),
    ])  # fmt: skip
    await add_claim(db, "n-1")
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("ignore_branch", "n-1"))
    assert await synthesis_claims(db, INV) == []
    await engine.submit(ncmd("restore_branch", "n-1"))
    assert (await inclusion(db))["n-1"] == "Included"
    assert [c.id for c in await synthesis_claims(db, INV)] == ["c-n-1"]
    row = (await db.read("SELECT status, verdict FROM nodes WHERE id = 'n-1'"))[0]
    assert row["status"] == "Completed" and row["verdict"]
    assert engine.model_client.calls == []  # nothing was re-run


async def test_restore_superseded_branch(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    await append_and_project(db, INV, [
        ev("node.inclusion_changed", {"node_ids": ["n-1"], "inclusion": "Superseded",
                                      "by": "replan", "instruction_id": "i-1"}),
    ])  # fmt: skip
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("restore_branch", "n-1"))
    assert (await inclusion(db))["n-1"] == "Included"
    row = (await db.read("SELECT excluded_by FROM nodes WHERE id = 'n-1'"))[0]
    assert row["excluded_by"] is None


async def test_restore_leaves_nodes_the_replan_superseded(db, tmp_path):
    await seed_tree(db)
    await append_and_project(db, INV, [
        ev("node.inclusion_changed", {"node_ids": ["n-1b"], "inclusion": "Superseded",
                                      "by": "replan", "instruction_id": "i-1"}),
    ])  # fmt: skip
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("ignore_branch", "n-1"))
    assert (await inclusion(db))["n-1b"] == "Superseded"  # not ignored a second time
    await engine.submit(ncmd("restore_branch", "n-1"))
    inc = await inclusion(db)
    assert inc["n-1"] == inc["n-1a"] == "Included" and inc["n-1b"] == "Superseded"


async def until(check):
    for _ in range(300):
        if await check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


async def test_pause_branch_leaves_rest_running(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("pause_branch", "n-1"))
    assert (await statuses(db))["n-1"] == "Paused"
    engine.start_runtime(INV)

    async def rest_done():
        return (await statuses(db))["n-2"] == "Completed"

    await until(rest_done)
    await asyncio.sleep(0.05)
    st = await statuses(db)
    assert st["n-1"] == "Paused"
    assert await state(db) == "Running"  # not finished: a branch the user paused is left
    assert (await events(db, "schedule.updated"))[0][2]["reasons"]["n-1"] == "paused"
    await engine.runtimes[INV].stop()


async def test_resume_branch(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    gate = asyncio.Event()
    script = {**BASE_SCRIPT, "node.decide:n-1": [decide("search", query="q"), conclude()]}
    client = TrackingClient(script, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(ncmd("pause_branch", "n-1"))
    gate.set()
    # The step finishes, then the node waits: the loop has nothing to start.
    for _ in range(200):
        await asyncio.sleep(0.01)
        if (await statuses(db))["n-1"] == "Paused" and not engine.runtimes[INV]._tasks:
            break
    assert (await statuses(db))["n-1"] == "Paused"
    assert len([c for c in client.calls if c.purpose == "node.decide"]) == 1
    await engine.submit(ncmd("resume_branch", "n-1"))
    await engine.runtimes[INV].wait()
    assert (await statuses(db))["n-1"] == "Completed"
    assert len(await events(db, "node.started")) == 1  # continued, not restarted


async def test_coordinator_aggregates_without_ignored_children(db, tmp_path):
    await seed_tree(db)
    # D1 is a coordinator waiting on its children D1a and D1b; D1b is ignored.
    await append_and_project(db, INV, [ev("node.waiting_on_children", {}, node_id="n-1")])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("ignore_branch", "n-1b"))
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()
    st = await statuses(db)
    assert st["n-1a"] == "Completed" and st["n-1b"] == "Pending"
    assert st["n-1"] == "Completed"  # aggregated over what was left (G3)
    assert await state(db) == "Completed"


async def test_duplicate_ignore_is_noop(db, tmp_path):
    await seed_tree(db)
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(ncmd("ignore_branch", "n-1"))
    before = len(await events(db))
    await engine.submit(ncmd("ignore_branch", "n-1"))
    assert len(await events(db)) == before
    c = ncmd("ignore_branch", "n-2")
    await engine.submit(c)
    ack = await engine.submit(c.model_copy())  # same command id
    assert ack.duplicate


async def test_branch_commands_are_refused_on_the_root(db, tmp_path):
    await seed_tree(db)
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    for t in ("ignore_branch", "restore_branch", "pause_branch", "resume_branch"):
        with pytest.raises(CommandRejected) as e:
            await engine.submit(ncmd(t, "n-r"))
        assert e.value.code == "use_investigation_controls"
    with pytest.raises(CommandRejected) as e:
        await engine.submit(cmd("ignore_branch"))
    assert e.value.code == "node_required"
