"""Running investigations survive a kill and restart (Phase 4, Task 8; 6.2, S7).

The kill: the runtime's tasks are cancelled (no handlers run on our side), the database is
closed, and a new Engine is built on the same data directory."""

import asyncio
import json
from collections import Counter

import pytest

from netgrip.adapters.fakes import FakeFetcher, FakeModelClient, FakeSearch
from netgrip.boundary.bus import EventBus
from netgrip.boundary.events import EventDraft
from netgrip.config import Config
from netgrip.engine.clock import FakeClock
from netgrip.engine.engine import Engine
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project
from netgrip.store.settings import DEFAULT_SETTINGS, SettingsModel, resolve_investigation_settings

INV = "inv-1"
NASA = "https://example.org/nasa/great-wall-from-orbit"
MYTH = "https://example.org/history/wall-myth"


def ev(type, data, node_id=None, actor="orchestrator"):
    return EventDraft(type=type, actor=actor, node_id=node_id, data=data)


def proposed(disp, kind="Divergent", parent="n-r", depth=1):
    return {"display_id": disp, "parent_id": parent, "kind": kind,
            "question": f"Question of {disp}", "justification": "needed",
            "depends_on": [], "depth": depth, "proposed_by": "orchestrator"}  # fmt: skip


def decide(action, **kw):
    return {"parsed": {"action": action, **kw}}


def conclude(text="It is hard to see"):
    return decide("conclude", verdict={"text": text, "confidence": "medium"}, open_questions=[])


def extraction(*claims):
    claims_ = [{"text": c, "stance": "supports"} for c in claims]
    return {"parsed": {"claims": claims_, "credibility": "Primary", "published_at": None,
                       "origin": "nasa.gov"}}  # fmt: skip


BASE = {
    "node.decide": [conclude()],
    "node.extract": [extraction("Hard to see")],
    "node.relevance": [{"parsed": {"relevant": True, "reason": "on topic"}}],
    "orchestrator.review": [{"parsed": {"decisions": []}}],
    "orchestrator.next": [{"parsed": {"decision": "conclude"}}],
    "evidence.match": [{"parsed": {"relation": "unrelated", "claim_id": None}}],
}


class Holding(FakeModelClient):
    """Answers, then never returns the n-th call of a held key ("purpose" or
    "purpose:node_ref"): the process is killed after the model call, before its commit."""

    def __init__(self, script, hold: dict | None = None, before: bool = False):
        super().__init__({**BASE, **script}, repeat_last=True)
        self.hold = hold or {}
        self.before = before
        self.counts: Counter = Counter()
        self.held = 0

    async def complete(self, req):
        keys = [f"{req.purpose}:{req.node_ref}", req.purpose]
        for k in keys:
            self.counts[k] += 1
        n = next(((k, self.hold[k]) for k in keys if k in self.hold), None)
        hit = n is not None and self.counts[n[0]] == n[1]
        if hit and self.before:
            self.held += 1
            await asyncio.Event().wait()
        resp = await super().complete(req)
        if hit:
            self.held += 1
            await asyncio.Event().wait()
        return resp


async def seed(db, nodes, parallel=4):
    g = SettingsModel.model_validate(DEFAULT_SETTINGS)
    settings = resolve_investigation_settings(g, {"effort": "Medium"})
    settings["effort_budget"]["parallel"] = parallel
    drafts = [
        ev("investigation.created", {"prompt": "p", "settings": settings}, actor="user"),
        ev("investigation.root_goal_set", {"root_goal": "Is the Great Wall visible?"}),
        ev("node.proposed", proposed("R", "Synthesis", parent=None, depth=0), node_id="n-r"),
        *(ev("node.proposed", proposed(d), node_id=nid) for nid, d in nodes),
        ev("node.approved", {"budget": {"sources": 3, "child_nodes": 3}}, node_id="n-r"),
        *(ev("node.approved", {"budget": {"sources": 3, "child_nodes": 2}}, node_id=nid)
          for nid, _ in nodes),
        ev("investigation.state_changed", {"from": "Draft", "to": "Planning", "origin": "user"}),
        ev("investigation.state_changed", {"from": "Planning", "to": "Running", "origin": "user"}),
    ]  # fmt: skip
    await append_and_project(db, INV, drafts)


def search():
    return FakeSearch({"default": [{"url": NASA, "title": "t", "snippet": "s"}]})


_open: list = []


@pytest.fixture(autouse=True)
async def close_all():
    """A failing test must not leave a connection thread behind (pytest would never exit)."""
    yield
    while _open:
        eng = _open.pop()
        try:
            await eng.stop()
            await eng.db.close()
        except Exception:
            pass


async def open_engine(tmp_path, client, fetcher=None, start=True):
    db = await open_db(tmp_path / "n.sqlite")
    eng = Engine(
        db, Config(data_dir=tmp_path / "data", fake=True), EventBus(), client,
        search=search(), fetcher=fetcher or FakeFetcher.from_scenario("great_wall_web"),
        clock=FakeClock(),
    )  # fmt: skip
    _open.append(eng)
    if start:
        await eng.start()
    return eng


async def kill(eng):
    await eng.stop()
    await eng.db.close()


async def until(pred, tries=3000):
    for _ in range(tries):
        if await pred():
            return
        await asyncio.sleep(0.001)
    raise AssertionError("condition never met")


async def events(db, type=None):
    rows = await db.read(
        "SELECT type, node_id, data FROM events WHERE investigation_id = ? ORDER BY seq", [INV]
    )
    out = [(r["type"], r["node_id"], json.loads(r["data"])) for r in rows]
    return [e for e in out if type is None or e[0] == type]


async def state(db):
    return (await db.read("SELECT state FROM investigations WHERE id = ?", [INV]))[0]["state"]


async def statuses(db):
    rows = await db.read("SELECT id, status FROM nodes WHERE investigation_id = ?", [INV])
    return {r["id"]: r["status"] for r in rows}


async def finish(eng):
    rt = eng.runtimes.get(INV)
    assert rt is not None
    await asyncio.wait_for(rt.wait(), 10)


# --- S7: eight running nodes -----------------------------------------------------------------

EIGHT = [f"n-{i}" for i in range(1, 9)]


async def eight_killed(tmp_path):
    """Eight nodes each read NASA (page and extraction committed), then are killed after their
    concluding model call, before its commit."""
    db = await open_db(tmp_path / "n.sqlite")
    await seed(db, [(n, f"D{i}") for i, n in enumerate(EIGHT, 1)], parallel=8)
    await db.close()
    script = {f"node.decide:{n}": [decide("read", url=NASA), conclude()] for n in EIGHT}
    client = Holding(script, {f"node.decide:{n}": 2 for n in EIGHT})
    eng = await open_engine(tmp_path, client)
    eng.start_runtime(INV)

    async def all_held():
        return client.held == 8

    await until(all_held)
    st = await statuses(eng.db)
    assert all(st[n] == "Running" for n in EIGHT)
    await kill(eng)


async def restarted(tmp_path, script=None):
    client = Holding(script or {f"node.decide:{n}": [decide("read", url=NASA), conclude()]
                                for n in EIGHT})  # fmt: skip
    fetcher = FakeFetcher.from_scenario("great_wall_web")
    eng = await open_engine(tmp_path, client, fetcher)
    return eng, client, fetcher


async def test_running_nodes_reset_and_rerun(tmp_path):
    await eight_killed(tmp_path)
    eng, client, _ = await restarted(tmp_path)
    resets = await events(eng.db, "node.reset")
    assert sorted(n for _, n, d in resets if d["reason"] == "recovery") == EIGHT
    *_, (_, _, rec) = await events(eng.db, "system.recovered")  # the first: an empty start
    assert sorted(rec["reset_node_ids"]) == EIGHT
    await finish(eng)
    st = await statuses(eng.db)
    assert all(st[n] == "Completed" for n in EIGHT)
    for n in EIGHT:
        assert client.counts[f"node.decide:{n}"] == 2  # ran again
    await eng.stop()
    await eng.db.close()


async def test_no_page_refetched_after_kill(tmp_path):
    await eight_killed(tmp_path)
    eng, _, fetcher = await restarted(tmp_path)
    await finish(eng)
    assert NASA not in fetcher.calls
    await eng.db.close()


async def test_no_extraction_repeated_after_kill(tmp_path):
    await eight_killed(tmp_path)
    eng, client, _ = await restarted(tmp_path)
    await finish(eng)
    assert client.counts["node.extract"] == 0  # D-07: every page version was extracted
    await eng.db.close()


async def test_run_completes_after_recovery(tmp_path):
    await eight_killed(tmp_path)
    eng, _, _ = await restarted(tmp_path)
    await finish(eng)
    assert await state(eng.db) == "Completed"
    assert len(await events(eng.db, "report.created")) == 1
    await eng.db.close()


# --- one node --------------------------------------------------------------------------------


async def one_node(tmp_path, nodes=(("n-1", "D1"),)):
    db = await open_db(tmp_path / "n.sqlite")
    await seed(db, list(nodes))
    await db.close()


@pytest.mark.parametrize("held", ["node.decide", "node.extract"])
async def test_kill_between_model_call_and_commit_duplicates_no_claim(tmp_path, held):
    """Killed after the model answered and before the step's commit: the step runs again on
    restart, and the claims are not duplicated."""
    await one_node(tmp_path)
    first = [decide("read", url=NASA), decide("read", url=MYTH), conclude()]
    hold = {"node.decide:n-1": 3} if held == "node.decide" else {"node.extract": 2}
    client = Holding({"node.decide:n-1": first,
                      "node.extract": [extraction("Hard to see"), extraction("A myth")]},
                     hold)  # fmt: skip
    eng = await open_engine(tmp_path, client)
    eng.start_runtime(INV)

    async def held_once():
        return client.held == 1

    await until(held_once)
    await kill(eng)
    again = Holding({"node.decide:n-1": first,
                     "node.extract": [extraction("A myth")]})  # fmt: skip
    eng = await open_engine(tmp_path, again)
    await finish(eng)
    claims = await eng.db.read("SELECT text FROM claims WHERE merged_into IS NULL")
    assert sorted(c["text"] for c in claims) == ["A myth", "Hard to see"]
    assert again.counts["node.decide:n-1"] == 3  # the interrupted step ran again
    assert await state(eng.db) == "Completed"
    await eng.db.close()


async def test_completed_nodes_untouched_after_kill(tmp_path):
    await one_node(tmp_path, (("n-1", "D1"), ("n-2", "D2")))
    client = Holding({}, {"node.decide:n-2": 1}, before=True)
    eng = await open_engine(tmp_path, client)
    eng.start_runtime(INV)

    async def n1_checked():
        return client.held == 1 and bool(
            [e for e in await events(eng.db, "node.relevance_checked") if e[1] == "n-1"]
        )

    await until(n1_checked)
    await kill(eng)
    again = Holding({})
    eng = await open_engine(tmp_path, again)
    await finish(eng)
    assert again.counts["node.decide:n-1"] == 0
    evs = await events(eng.db)
    assert [t for t, n, _ in evs if n == "n-1" and t == "node.started"] == ["node.started"]
    assert [t for t, n, _ in evs if n == "n-1" and t == "node.completed"] == ["node.completed"]
    assert [n for t, n, d in evs if t == "node.reset"] == ["n-2"]
    assert await state(eng.db) == "Completed"
    await eng.db.close()


async def test_paused_investigation_stays_paused(tmp_path):
    await one_node(tmp_path)
    db = await open_db(tmp_path / "n.sqlite")
    await append_and_project(db, INV, [
        ev("node.started", {"attempt": 1, "brief": {}}, node_id="n-1", actor="node"),
        ev("node.reset", {"reason": "outage"}, node_id="n-1", actor="system"),
        ev("investigation.state_changed", {"from": "Running", "to": "Paused", "origin": "system",
                                           "cause": "model_unavailable", "detail": "down"},
           actor="system"),
    ])  # fmt: skip
    await db.close()
    client = Holding({})
    eng = await open_engine(tmp_path, client)
    await asyncio.sleep(0.01)
    assert await state(eng.db) == "Paused"
    assert INV not in eng.runtimes
    assert await events(eng.db, "system.recovered") == []
    assert (await statuses(eng.db))["n-1"] == "Pending"
    assert not client.calls
    await eng.db.close()


async def test_state_mismatch_triggers_rebuild(tmp_path):
    await one_node(tmp_path)
    client = Holding({}, {"node.decide:n-1": 1})
    eng = await open_engine(tmp_path, client)
    eng.start_runtime(INV)

    async def held():
        return client.held == 1

    await until(held)
    await kill(eng)
    db = await open_db(tmp_path / "n.sqlite")
    # The state tables disagree with the log: n-1 shows Completed, last_seq is behind.
    async with db.tx() as tx:
        await tx.execute("UPDATE nodes SET status = 'Completed' WHERE id = 'n-1'")
        await tx.execute("UPDATE investigations SET last_seq = last_seq - 1")
    await db.close()
    again = Holding({})
    eng = await open_engine(tmp_path, again)
    assert [n for t, n, d in await events(eng.db, "node.reset")] == ["n-1"]
    await finish(eng)
    assert again.counts["node.decide:n-1"] == 1
    assert await state(eng.db) == "Completed"
    await eng.db.close()


async def test_synthesising_restarts_synthesis(tmp_path):
    await one_node(tmp_path)
    db = await open_db(tmp_path / "n.sqlite")
    await append_and_project(db, INV, [ev("investigation.state_changed", {
        "from": "Running", "to": "Synthesising", "origin": "orchestrator"})])  # fmt: skip
    await db.close()
    eng = await open_engine(tmp_path, Holding({}))
    await until(lambda: _completed(eng))
    assert len(await events(eng.db, "report.created")) == 1
    await eng.db.close()


async def _completed(eng):
    return await state(eng.db) == "Completed"


# --- return work owed when the process died ----------------------------------------------------


async def test_relevance_gate_redone_after_kill(tmp_path):
    await one_node(tmp_path)
    client = Holding({}, {"node.relevance": 1}, before=True)
    eng = await open_engine(tmp_path, client)
    eng.start_runtime(INV)

    async def held():
        return client.held == 1

    await until(held)
    await kill(eng)
    again = Holding({"node.relevance": [{"parsed": {"relevant": False, "reason": "astray"}}]})
    eng = await open_engine(tmp_path, again)
    await finish(eng)
    assert again.counts["node.decide:n-1"] == 0  # never re-run
    assert [n for _, n, _ in await events(eng.db, "node.off_topic")] == ["n-1"]
    assert await state(eng.db) == "Completed"
    await eng.db.close()


async def test_proposals_reviewed_after_kill(tmp_path):
    await one_node(tmp_path)
    split = decide("split", children=[{"question": "Who said it first?"}])
    client = Holding({"node.decide:n-1": [split, conclude("Combined")]},
                     {"orchestrator.review": 1}, before=True)  # fmt: skip
    eng = await open_engine(tmp_path, client)
    eng.start_runtime(INV)

    async def held():
        return client.held == 1

    await until(held)
    await kill(eng)
    again = Holding({"node.decide:n-1": [conclude("Combined")]})
    eng = await open_engine(tmp_path, again)
    await finish(eng)
    assert again.counts["orchestrator.review"] == 1
    st = await statuses(eng.db)
    assert st["n-1"] == "Completed"
    assert "Proposed" not in st.values()
    assert await state(eng.db) == "Completed"
    await eng.db.close()
