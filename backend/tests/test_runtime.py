import asyncio
import json
import uuid

import pytest

from netgrip.adapters.fakes import FakeFetcher, FakeModelClient, FakeSearch
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command, CommandRejected
from netgrip.boundary.events import EventDraft
from netgrip.config import Config
from netgrip.engine import limiter
from netgrip.engine.clock import FakeClock
from netgrip.engine.engine import Engine
from netgrip.engine.scheduler import GraphNode, eligible, schedule
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project
from netgrip.store.settings import DEFAULT_SETTINGS, SettingsModel, resolve_investigation_settings

INV = "inv-1"


def ev(type, data, node_id=None, actor="orchestrator"):
    return EventDraft(type=type, actor=actor, node_id=node_id, data=data)


def proposed(disp, kind="Divergent", parent="n-r", depth=1, depends_on=(), question=None):
    return {"display_id": disp, "parent_id": parent, "kind": kind,
            "question": question or f"Question of {disp}", "justification": "needed",
            "depends_on": list(depends_on), "depth": depth,
            "proposed_by": "orchestrator"}  # fmt: skip


def decide(action, **kw):
    return {"parsed": {"action": action, **kw}}


def conclude(text="It is hard to see", confidence="medium"):
    return decide("conclude", verdict={"text": text, "confidence": confidence}, open_questions=[])


BASE_SCRIPT = {
    "node.decide": [conclude()],
    "node.relevance": [{"parsed": {"relevant": True, "reason": "on topic"}}],
    "orchestrator.review": [{"parsed": {"decisions": []}}],
    "orchestrator.next": [{"parsed": {"decision": "conclude"}}],
    "evidence.match": [{"parsed": {"relation": "unrelated", "claim_id": None}}],
}


class TrackingClient(FakeModelClient):
    """Yields inside every call and records how many node.decide calls overlap."""

    def __init__(self, script, gate: asyncio.Event | None = None):
        super().__init__(script, repeat_last=True)
        self.active: dict[str, int] = {}
        self.peak: dict[str, int] = {}
        self.model_in_use_peak = 0
        self.gate = gate
        self.entered = asyncio.Event()

    async def complete(self, req):
        p = req.purpose
        self.active[p] = self.active.get(p, 0) + 1
        self.peak[p] = max(self.peak.get(p, 0), self.active[p])
        self.model_in_use_peak = max(self.model_in_use_peak, limiter.model.in_use)
        try:
            self.entered.set()
            if self.gate is not None:
                await self.gate.wait()
            for _ in range(5):
                await asyncio.sleep(0)
            return await super().complete(req)
        finally:
            self.active[p] -= 1


class CrowdingClient(TrackingClient):
    """Holds each call until the model pool is full (or briefly), so calls overlap."""

    async def complete(self, req):
        for _ in range(200):
            if limiter.model.in_use >= limiter.model.capacity:
                break
            await asyncio.sleep(0.001)
        return await super().complete(req)


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


async def seed(db, nodes, inv=INV, effort="Medium", root="n-r"):
    """An approved, Running investigation with root n-r and `nodes`: (id, proposed-data)."""
    g = SettingsModel.model_validate(DEFAULT_SETTINGS)
    settings = resolve_investigation_settings(g, {"effort": effort})
    drafts = [
        ev("investigation.created", {"prompt": "p", "settings": settings}, actor="user"),
        ev("investigation.root_goal_set", {"root_goal": "Is the Great Wall visible?"}),
        ev("node.proposed", proposed("R", "Synthesis", parent=None, depth=0), node_id=root),
        *(ev("node.proposed", data | {"parent_id": root}, node_id=nid) for nid, data in nodes),
        ev("node.approved", {"budget": {"sources": 2, "child_nodes": 3}}, node_id=root),
        *(ev("node.approved", {"budget": {"sources": 2, "child_nodes": 2}}, node_id=nid)
          for nid, _ in nodes),
        ev("investigation.state_changed", {"from": "Draft", "to": "Planning", "origin": "user"}),
        ev("investigation.state_changed", {"from": "Planning", "to": "Running", "origin": "user"}),
    ]  # fmt: skip
    await append_and_project(db, inv, drafts)


def make_engine(db, tmp_path, client):
    return Engine(
        db,
        Config(data_dir=tmp_path / "data", fake=True),
        EventBus(),
        client,
        search=FakeSearch({"default": []}),
        fetcher=FakeFetcher({}),
        clock=FakeClock(),
    )


async def events(db, type=None, inv=INV):
    rows = await db.read(
        "SELECT type, node_id, data FROM events WHERE investigation_id = ? ORDER BY seq", [inv]
    )
    out = [(r["type"], r["node_id"], json.loads(r["data"])) for r in rows]
    return [e for e in out if type is None or e[0] == type]


async def state(db, inv=INV):
    return (await db.read("SELECT state FROM investigations WHERE id = ?", [inv]))[0]["state"]


async def statuses(db, inv=INV):
    rows = await db.read("SELECT id, status FROM nodes WHERE investigation_id = ?", [inv])
    return {r["id"]: r["status"] for r in rows}


def started(evs):
    return [n for t, n, _ in evs if t == "node.started"]


def cmd(type, **payload):
    return Command(id=uuid.uuid4(), type=type, investigation_id=INV, payload=payload)


# --- scheduler (pure) ------------------------------------------------------------------------


def gn(id, status="Pending", kind="Divergent", depth=1, seq=0, parent="r", deps=(), **kw):
    return GraphNode(id=id, status=status, kind=kind, depth=depth, seq=seq, parent_id=parent,
                     depends_on=tuple(deps), **kw)  # fmt: skip


def test_dependencies_gate_start():
    graph = [gn("r", "Pending", "Synthesis", 0, 0, None), gn("a", seq=1),
             gn("b", seq=2, deps=["a"])]  # fmt: skip
    assert eligible(graph) == ["a"]
    done = [graph[0], gn("a", "Completed", seq=1), graph[2]]
    assert eligible(done) == ["b"]


def test_premise_checks_run_first():
    graph = [gn("r", kind="Synthesis", depth=0, parent=None), gn("deep", depth=1, seq=1),
             gn("d2", depth=2, seq=2, parent="deep"), gn("p", kind="Premise check", depth=1, seq=5),
             gn("d1", depth=1, seq=3)]  # fmt: skip
    assert eligible(graph) == ["p", "deep", "d1", "d2"]


def test_schedule_updated_carries_wait_reasons():
    graph = [gn("r", kind="Synthesis", depth=0, parent=None), gn("a", seq=1), gn("b", seq=2),
             gn("c", seq=3, deps=["a"]), gn("x", "Proposed", seq=4),
             gn("y", "Rejected", seq=5)]  # fmt: skip
    s = schedule(graph, 1)
    assert s.order == ["a", "b"]
    assert s.reasons == {"b": "slot", "c": "dependency:a", "x": "orchestrator"}
    assert s.slots == 1


# --- runtime ---------------------------------------------------------------------------------


async def run_to_end(engine):
    engine.start_runtime(INV)
    await engine.runtimes[INV].wait()


async def test_parallelism_never_exceeds_effort(db, tmp_path):
    await seed(db, [(f"n-{i}", proposed(f"D{i}")) for i in range(1, 6)], effort="Low")
    client = TrackingClient(BASE_SCRIPT)
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    evs = await events(db)
    running = peak = 0
    for t, _, _ in evs:
        running += {"node.started": 1, "node.completed": -1, "node.failed": -1}.get(t, 0)
        peak = max(peak, running)
    assert peak == 2  # Low effort: parallel 2
    assert len(started(evs)) == 5


async def test_global_model_limiter_shared_by_two_investigations(db, tmp_path):
    await seed(db, [(f"n-{i}", proposed(f"D{i}")) for i in range(1, 5)])
    await seed(db, [(f"m-{i}", proposed(f"E{i}")) for i in range(1, 5)], inv="inv-2", root="m-r")
    client = CrowdingClient(BASE_SCRIPT)
    engine = make_engine(db, tmp_path, client)
    old = limiter.model.capacity
    limiter.model.resize(2)
    try:
        engine.start_runtime(INV)
        engine.start_runtime("inv-2")
        await engine.runtimes[INV].wait()
        await engine.runtimes["inv-2"].wait()
    finally:
        limiter.model.resize(old)
    assert client.model_in_use_peak == 2
    assert await state(db) == await state(db, "inv-2") == "Completed"


async def test_coordinator_waits_then_aggregates(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    script = dict(BASE_SCRIPT)
    script["node.decide:n-1"] = [decide("split", children=[{"question": "Who said it first?"}]),
                                 conclude("Combined answer")]  # fmt: skip
    client = TrackingClient(script)
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    evs = await events(db)
    [child] = [n for t, n, d in evs if t == "node.proposed" and d["parent_id"] == "n-1"]
    types = [(t, n) for t, n, _ in evs]
    child_done = types.index(("node.completed", child))
    aggregating = next(
        i
        for i, (t, n, d) in enumerate(evs)
        if t == "node.activity" and n == "n-1" and d["activity"] == "Aggregating"
    )
    assert child_done < aggregating
    # The child's result was checked on return before the parent aggregated.
    purposes = [(c.purpose, c.node_ref) for c in client.calls]
    relevance_for_child = next(
        i
        for i, c in enumerate(client.calls)
        if c.purpose == "node.relevance" and "Who said it first?" in c.messages[0].content
    )
    aggregate_call = max(i for i, p in enumerate(purposes) if p == ("node.decide", "n-1"))
    assert relevance_for_child < aggregate_call
    st = await statuses(db)
    assert st["n-1"] == "Completed" and st[child] == "Completed"


async def test_schedule_updated_emitted_with_reasons(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2")),
                    ("n-3", proposed("D3", depends_on=["n-1"]))], effort="Low")  # fmt: skip
    client = TrackingClient(BASE_SCRIPT)
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    first = (await events(db, "schedule.updated"))[0][2]
    assert first["order"][:2] == ["n-1", "n-2"]
    assert first["reasons"]["n-3"] == "dependency:n-1"
    assert started(await events(db)).index("n-3") > started(await events(db)).index("n-1")


async def test_pause_lets_steps_finish_then_pauses(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    gate = asyncio.Event()
    client = TrackingClient(BASE_SCRIPT, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(cmd("pause"))
    assert await state(db) == "Running"  # steps in flight still finishing
    gate.set()
    await engine.runtimes[INV].wait()
    [last] = (await events(db, "investigation.state_changed"))[-1:]
    assert last[2]["to"] == "Paused" and last[2]["origin"] == "user"
    assert last[2]["cause"] == "user"
    # The in-flight decisions committed; no further step started after the pause.
    calls = len(client.calls)
    await asyncio.sleep(0)
    assert len(client.calls) == calls
    steps = await events(db, "node.step_completed")
    assert len(steps) >= 1


async def test_resume_continues(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    gate = asyncio.Event()
    client = TrackingClient(BASE_SCRIPT, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(cmd("pause"))
    gate.set()
    await engine.runtimes[INV].wait()
    assert await state(db) == "Paused"
    with pytest.raises(CommandRejected):
        await engine.submit(cmd("pause"))
    await engine.submit(cmd("resume"))
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"
    assert (await statuses(db))["n-1"] == "Completed"
    assert len(started(await events(db))) == 2  # continued, not restarted


async def test_stop_keeps_everything_and_can_resume(db, tmp_path):
    await seed(db, [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    gate = asyncio.Event()
    client = TrackingClient(BASE_SCRIPT, gate=gate)
    engine = make_engine(db, tmp_path, client)
    engine.start_runtime(INV)
    await client.entered.wait()
    await engine.submit(cmd("stop"))
    assert await state(db) == "Stopped"
    gate.set()
    await engine.runtimes[INV].wait()
    assert await state(db) == "Stopped"
    nodes = await statuses(db)
    assert set(nodes) == {"n-r", "n-1", "n-2"}  # nothing deleted
    count = len(await events(db))
    await asyncio.sleep(0)
    assert len(await events(db)) == count
    await engine.submit(cmd("resume"))
    await engine.runtimes[INV].wait()
    assert await state(db) == "Completed"


async def test_raise_limit_emits_limit_changed(db, tmp_path):
    await seed(db, [("n-1", proposed("D1"))])
    engine = make_engine(db, tmp_path, TrackingClient(BASE_SCRIPT))
    await engine.submit(cmd("raise_limit", spending_limit_usd=12.5))
    assert (await events(db, "limit.changed"))[-1][2] == {"spending_limit_usd": 12.5}
    row = await db.read("SELECT spending_limit_usd FROM investigations WHERE id = ?", [INV])
    assert row[0][0] == 12.5
    with pytest.raises(CommandRejected) as e:
        await engine.submit(cmd("raise_limit", spending_limit_usd=-1))
    assert e.value.code == "invalid_limit"


async def test_run_reaches_completed(db, tmp_path):
    await seed(db, [("n-p", proposed("P1", "Premise check")), ("n-1", proposed("D1")),
                    ("n-2", proposed("D2", depends_on=["n-p"]))])  # fmt: skip
    client = TrackingClient(BASE_SCRIPT)
    engine = make_engine(db, tmp_path, client)
    await run_to_end(engine)
    assert await state(db) == "Completed"
    st = await statuses(db)
    assert all(st[n] == "Completed" for n in ("n-p", "n-1", "n-2"))
    assert started(await events(db))[0] == "n-p"
    changes = [(d["from"], d["to"]) for _, _, d in await events(db, "investigation.state_changed")]
    assert changes[-2:] == [("Running", "Synthesising"), ("Synthesising", "Completed")]
    [(_, _, report)] = await events(db, "report.created")
    assert set(report) == {"report_id", "ended_early", "cut_short_by"}
    assert report["ended_early"] is False and report["cut_short_by"] is None
    relevance = [c for c in client.calls if c.purpose == "node.relevance"]
    assert len(relevance) == 3  # every Completed node checked before synthesis
