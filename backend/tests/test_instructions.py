"""Instructions on a running investigation (domain 4.9, U1-U6, E4, S4)."""

import asyncio
import json
import uuid

import pytest
from test_runtime import (
    BASE_SCRIPT,
    INV,
    TrackingClient,
    conclude,
    decide,
    ev,
    events,
    make_engine,
    proposed,
    seed,
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


def icmd(node_id, text="Concentrate on the NASA sources"):
    return Command(
        id=uuid.uuid4(), type="add_instruction", investigation_id=INV, node_id=node_id,
        payload={"text": text},
    )  # fmt: skip


async def until(check):
    for _ in range(400):
        if await check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("timed out")


def child(ref, question=None, **kw):
    return {"ref": ref, "kind": "Divergent", "question": question or f"Question of {ref}",
            "justification": "needed", "out_of_scope": "", "done_when": "answered",
            "depends_on_refs": [], **kw}  # fmt: skip


def replan(*children):
    return {"parsed": {"children": list(children)}}


async def seed_coordinator(db, n=5):
    """D1 waits on D1a..: its children are approved and pending."""
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    drafts = [ev("node.waiting_on_children", {}, node_id="n-1")]
    for i in range(n):
        letter = "abcdefgh"[i]
        nid = f"n-1{letter}"
        drafts += [
            ev("node.proposed", {**proposed(f"D1{letter}", parent="n-1", depth=2),
                                 "question": f"Question of D1{letter}", "out_of_scope": "",
                                 "done_when": "answered"}, node_id=nid),
            ev("node.approved", {"budget": {"sources": 2, "child_nodes": 0}}, node_id=nid),
        ]  # fmt: skip
    await append_and_project(db, INV, drafts)


async def instruction_state(db):
    rows = await db.read("SELECT id, state, node_id FROM instructions")
    return {r["node_id"]: r["state"] for r in rows}


async def test_instruction_waits_for_step_boundary(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    gate = asyncio.Event()
    script = {**BASE_SCRIPT, "node.decide:n-1": [decide("search", query="q"), conclude()]}
    client = TrackingClient(script, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(icmd("n-1", "Look at photographs only"))
    [(_, _, queued)] = await events(db, "instruction.queued")
    assert queued["waiting_for"].startswith("D1 finishes")
    assert await events(db, "instruction.applied") == []
    gate.set()
    await engine.runtimes[INV].wait()
    calls = [c for c in client.calls if c.purpose == "node.decide" and c.node_ref == "n-1"]
    assert "Look at photographs only" not in calls[0].messages[0].content  # old brief
    assert "Look at photographs only" in calls[1].messages[0].content  # next step
    [(_, _, applied)] = await events(db, "instruction.applied")
    assert applied["at_step"] == 1
    row = (await db.read("SELECT instruction_count FROM nodes WHERE id = 'n-1'"))[0]
    assert row["instruction_count"] == 1


async def test_instruction_on_coordinator_keeps_supersedes_proposes(db, tmp_path):
    await seed_coordinator(db)
    data = {"claim_id": "c-keep", "text": "Kept claim", "status": "Supported",
            "supporting": [], "contradicting": []}  # fmt: skip
    await append_and_project(db, INV, [ev("claim.added", data, node_id="n-1a", actor="node")])
    script = {**BASE_SCRIPT, "node.replan": [replan(child("D1a", "Question of D1a"),
                                                     child("D1f", "New focus"))]}  # fmt: skip
    engine = make_engine(db, tmp_path, TrackingClient(script))
    await engine.submit(icmd("n-1"))

    async def applied():
        return bool(await events(db, "instruction.applied"))

    await until(applied)
    [(_, _, d)] = await events(db, "instruction.applied")
    assert d["diff"]["kept"] == ["n-1a"]
    assert sorted(d["diff"]["superseded"]) == ["n-1b", "n-1c", "n-1d", "n-1e"]
    [new] = d["diff"]["proposed"]
    rows = await db.read("SELECT id, inclusion, status, question FROM nodes WHERE parent_id='n-1'")
    by = {r["id"]: r for r in rows}
    assert [by[i]["inclusion"] for i in d["diff"]["superseded"]] == ["Superseded"] * 4
    assert by["n-1a"]["inclusion"] == "Included"
    assert by[new]["question"] == "New focus"
    assert [c.id for c in await synthesis_claims(db, INV)] == ["c-keep"]  # kept keeps claims
    [(_, _, sup)] = await events(db, "node.inclusion_changed")
    assert sup["by"] == "replan" and sup["instruction_id"]
    calls = [c for c in engine.model_client.calls if c.purpose == "node.replan"]
    assert len(calls) == 1 and "Concentrate on the NASA" in calls[0].messages[0].content
    assert calls[0].tier == "standard"


async def test_superseded_children_restorable(db, tmp_path):
    await seed_coordinator(db, 2)
    script = {**BASE_SCRIPT, "node.replan": [replan(child("D1a", "Question of D1a"))]}
    engine = make_engine(db, tmp_path, TrackingClient(script))
    await engine.submit(icmd("n-1"))

    async def applied():
        return bool(await events(db, "instruction.applied"))

    await until(applied)
    assert (await db.read("SELECT inclusion FROM nodes WHERE id='n-1b'"))[0][0] == "Superseded"
    await engine.submit(Command(id=uuid.uuid4(), type="restore_branch", investigation_id=INV,
                                node_id="n-1b"))  # fmt: skip
    assert (await db.read("SELECT inclusion FROM nodes WHERE id='n-1b'"))[0][0] == "Included"


async def test_edited_kept_child_is_retried_then_gives_up(db, tmp_path):
    await seed_coordinator(db, 2)
    bad = replan(child("D1a", "Changed question"), child("D1b", "Question of D1b"))
    script = {**BASE_SCRIPT, "node.replan": [bad]}
    client = TrackingClient(script)
    engine = make_engine(db, tmp_path, client)
    await engine.submit(icmd("n-1"))

    async def applied():
        return bool(await events(db, "instruction.applied"))

    await until(applied)
    [(_, _, d)] = await events(db, "instruction.applied")
    assert d["diff"]["superseded"] == [] and d["diff"]["notes"]
    assert len([c for c in client.calls if c.purpose == "node.replan"]) == 3


async def test_instruction_inherited_by_descendants_briefs(db, tmp_path):
    await seed_coordinator(db, 1)
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(icmd("n-2"))  # a leaf elsewhere: applied at once
    script = {**BASE_SCRIPT, "node.replan": [replan(child("D1a", "Question of D1a"))]}
    engine = make_engine(db, tmp_path, TrackingClient(script))
    await engine.submit(icmd("n-1", "Prefer primary sources"))

    async def applied():
        return len(await events(db, "instruction.applied")) == 2

    await until(applied)
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()
    brief = await events(db, "node.started")
    mine = [d["brief"] for _, n, d in brief if n == "n-1a"][0]
    assert [i["text"] for i in mine["known"]["instructions"]] == ["Prefer primary sources"]
    assert mine["known"]["instructions"][0]["from_display_id"] == "D1"


async def test_two_instructions_apply_in_order(db, tmp_path):
    await seed_coordinator(db, 3)
    script = {**BASE_SCRIPT, "node.replan": [
        replan(child("D1a", "Question of D1a"), child("D1b", "Question of D1b")),
        replan(child("D1a", "Question of D1a")),
    ]}  # fmt: skip
    client = TrackingClient(script)
    engine = make_engine(db, tmp_path, client)
    await engine.submit(icmd("n-1", "first"))
    await engine.submit(icmd("n-1", "second"))

    async def both():
        return len(await events(db, "instruction.applied")) == 2

    await until(both)
    first, second = [d for _, _, d in await events(db, "instruction.applied")]
    assert first["diff"]["superseded"] == ["n-1c"]
    assert second["diff"]["superseded"] == ["n-1b"]  # saw the result of the first
    replans = [c for c in client.calls if c.purpose == "node.replan"]
    assert len(replans) == 2
    assert "first" in replans[1].messages[0].content and "second" in replans[1].messages[0].content


async def test_instruction_on_node_that_completes_first_is_applied_not_stuck(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    gate = asyncio.Event()
    client = TrackingClient(BASE_SCRIPT, gate=gate)  # one step: conclude
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(icmd("n-1"))
    gate.set()
    await engine.runtimes[INV].wait()
    assert (await statuses(db))["n-1"] == "Completed"
    assert await instruction_state(db) == {"n-1": "applied"}


async def test_root_locked_after_approval(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    with pytest.raises(CommandRejected) as e:
        await engine.submit(icmd("n-r"))
    assert e.value.code == "root_locked"


async def test_instruction_text_is_framed_as_scope_not_conclusion(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    await engine_with_instruction(db, tmp_path)


async def engine_with_instruction(db, tmp_path):
    client = TrackingClient(BASE_SCRIPT)
    engine = make_engine(db, tmp_path, client)
    await engine.submit(icmd("n-1", "The Wall is plainly visible"))

    async def applied():
        return bool(await events(db, "instruction.applied"))

    await until(applied)
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()
    text = next(c for c in client.calls if c.purpose == "node.decide").messages[0].content
    assert "Instructions from the user that apply." in text
    assert "scope guidance" in text and "treat it as a hypothesis to check" in text
    assert json.dumps("The Wall is plainly visible")[1:-1] in text
