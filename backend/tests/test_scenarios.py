"""Engine scenarios on the fake Great Wall run (Phase 4, Task 9): the plan NETGRIP_FAKE=1
drafts, approved and run to Completed on the scripted web."""

import asyncio
import json

from great_wall_run import MYTH, NASA, GatedFetcher, open_engine, run

from netgrip.adapters.fakes import FakeModelClient
from netgrip.api.investigations import list_investigations

D1A = (
    "Which astronauts have said whether they saw the Wall from low Earth orbit, and with what aid?"
)
D1B = "What did Yang Liwei report about the Wall after Shenzhou 5?"


async def events(db, inv, type=None):
    rows = await db.read(
        "SELECT seq, type, node_id, data FROM events WHERE investigation_id = ? ORDER BY seq",
        [inv],
    )
    out = [(r["seq"], r["type"], r["node_id"], json.loads(r["data"])) for r in rows]
    return [e for e in out if type is None or e[1] == type]


async def nodes(db, inv):
    rows = await db.read("SELECT * FROM nodes WHERE investigation_id = ? ORDER BY seq", [inv])
    return {r["display_id"]: dict(r) for r in rows}


async def row(db, inv):
    return next(r for r in await list_investigations(db) if r["id"] == inv)


async def test_s1_wrong_premise(tmp_path):
    engine = await open_engine(tmp_path)
    try:
        r = run(engine)
        await r.approved()
        await r.finished()
        db, inv = engine.db, r.inv
        assert (await row(db, inv))["state"] == "Completed"
        p1 = (await nodes(db, inv))["P1"]
        assert p1["kind"] == "Premise check" and p1["status"] == "Completed"
        [(_, _, node_id, outcome)] = await events(db, inv, "premise.outcome")
        assert node_id == p1["id"] and outcome["outcome"] == "refuted"
        premise = (await db.read("SELECT * FROM premises WHERE investigation_id = ?", [inv]))[0]
        assert premise["outcome"] == "refuted"
        # P1 read both pages it found, the second after two timeouts, and recorded claims.
        reads = [d["detail"] for _, _, n, d in await events(db, inv, "node.activity")
                 if n == p1["id"] and d["activity"] == "Reading"]  # fmt: skip
        assert reads == [NASA, MYTH]
        retries = [d["retry"] for _, _, n, d in await events(db, inv, "node.activity")
                   if n == p1["id"] and d["activity"] == "Retrying"]  # fmt: skip
        assert retries == [{"n": 2, "m": 3}, {"n": 3, "m": 3}]
        claims = await db.read("SELECT text FROM claims WHERE node_id = ?", [p1["id"]])
        assert len(claims) == 3
        summary = (await row(db, inv))["summary"]
        assert summary == f"Premise refuted: {premise['text']}"
    finally:
        await engine.stop()
        await engine.db.close()


class Rendezvous(FakeModelClient):
    """Holds the first decision of each of `questions` until all of them have asked: they
    can only all arrive if they run at the same time."""

    def __init__(self, questions: list[str]) -> None:
        base = FakeModelClient.from_scenario("great_wall", repeat_last=True)
        super().__init__(base.queues, repeat_last=True)
        self.waiting = {q: asyncio.Event() for q in questions}

    async def complete(self, req):
        prompt = req.messages[0].content or ""
        mine = next((q for q in self.waiting if f"Your task: {q}" in prompt), None)
        if req.purpose == "node.decide" and mine and not self.waiting[mine].is_set():
            self.waiting[mine].set()
            await asyncio.wait_for(
                asyncio.gather(*(e.wait() for e in self.waiting.values())), timeout=5
            )
        return await super().complete(req)


async def test_s2_divergent_then_deep(tmp_path):
    engine = await open_engine(tmp_path, model=Rendezvous([D1A, D1B]))
    try:
        r = run(engine)
        await r.approved()
        await r.finished()
        db, inv = engine.db, r.inv
        assert (await row(db, inv))["state"] == "Completed"
        by_display = await nodes(db, inv)
        d1 = by_display["D1"]
        assert d1["kind"] == "Divergent" and d1["status"] == "Completed"
        lines = [n for n in by_display.values() if n["parent_id"] == d1["id"]]
        assert [(n["display_id"], n["kind"], n["question"]) for n in lines] == [
            ("D1a", "Deep-dive", D1A),
            ("D1b", "Deep-dive", D1B),
        ]
        assert all(n["status"] == "Completed" and n["proposed_by"] == d1["id"] for n in lines)
        evs = await events(db, inv)
        ids = {n["id"] for n in lines}
        approved = [s for s, t, n, _ in evs if t == "node.approved" and n in ids]
        started = [s for s, t, n, _ in evs if t == "node.started" and n in ids]
        completed = [s for s, t, n, _ in evs if t == "node.completed" and n in ids]
        assert len(approved) == len(started) == len(completed) == 2
        assert max(approved) < min(started)  # approved by the orchestrator, then run
        assert max(started) < min(completed)  # both running at once
        # D1 waited on its lines, then aggregated them into its own verdict.
        d1_completed = next(s for s, t, n, _ in evs if t == "node.completed" and n == d1["id"])
        assert d1_completed > max(completed)
        assert any(t == "node.activity" and n == d1["id"] and d["activity"] == "Aggregating"
                   for _, t, n, d in evs)  # fmt: skip
    finally:
        await engine.stop()
        await engine.db.close()


async def test_list_row_summary_per_state(tmp_path):
    held = asyncio.Event()
    release = asyncio.Event()

    async def hold() -> None:
        held.set()
        await release.wait()

    engine = await open_engine(tmp_path, fetcher=GatedFetcher(MYTH, hold), parallel=1)
    try:
        r = run(engine)
        await r.approved()
        await asyncio.wait_for(held.wait(), 10)
        db, inv = engine.db, r.inv
        running = await row(db, inv)
        assert running["state"] == "Running"
        assert running["running_count"] == 1
        assert running["summary"] == "P1 Reading"
        assert running["nodes_total"] == 6

        await r.submit("pause")
        release.set()
        await r.finished()
        paused = await row(db, inv)
        assert (paused["state"], paused["pause_cause"]) == ("Paused", "user")
        assert paused["running_count"] == 0
        assert paused["summary"] == "Paused by you."

        await r.submit("resume")
        await r.finished()
        assert (await row(db, inv))["state"] == "Completed"
    finally:
        await engine.stop()
        await engine.db.close()


async def test_deleting_a_running_investigation_stops_its_runtime(tmp_path):
    held = asyncio.Event()
    release = asyncio.Event()

    async def hold() -> None:
        held.set()
        await release.wait()

    engine = await open_engine(tmp_path, fetcher=GatedFetcher(NASA, hold))
    try:
        r = run(engine)
        await r.approved()
        await asyncio.wait_for(held.wait(), 10)
        await engine.delete_investigation(r.inv)
        assert r.inv not in engine.runtimes
        release.set()
        await asyncio.sleep(0.05)
        assert (
            await engine.db.read("SELECT 1 FROM events WHERE investigation_id = ?", [r.inv]) == []
        )
    finally:
        await engine.stop()
        await engine.db.close()


async def test_abandoning_a_runtime_awaits_its_cancelled_node_tasks(tmp_path):
    held = asyncio.Event()

    async def hold() -> None:
        held.set()
        await asyncio.Event().wait()  # never returns: only a cancel ends it

    engine = await open_engine(tmp_path, fetcher=GatedFetcher(NASA, hold))
    try:
        r = run(engine)
        await r.approved()
        await asyncio.wait_for(held.wait(), 10)
        rt = engine.runtimes[r.inv]
        tasks = list(rt._tasks.values())
        assert tasks
        await rt.stop(abandon=True)
        assert all(t.done() for t in tasks)
    finally:
        await engine.stop()
        await engine.db.close()


async def test_snapshot_counts_the_claims_synthesis_uses(tmp_path):
    """ScreenControlBoard, Synthesising: "Writing the report from N claims"."""
    from netgrip.api.investigations import snapshot
    from netgrip.engine.orchestrator import synthesis_claims

    engine = await open_engine(tmp_path)
    try:
        r = run(engine)
        await r.approved()
        await r.finished()
        snap = await snapshot(r.inv, engine.db)
        n = len(await synthesis_claims(engine.db, r.inv))
        assert n > 0
        assert snap["synthesis_claims"] == n
    finally:
        await engine.stop()
        await engine.db.close()
