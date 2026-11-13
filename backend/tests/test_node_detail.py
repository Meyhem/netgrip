"""Phase 5 Task 1: node detail, stored page text, live model text and event paging."""

import json

import pytest

from netgrip.adapters.fakes import FakeFetcher, FakeModelClient, FakeSearch
from netgrip.boundary.bus import Ephemeral
from netgrip.boundary.events import EventDraft
from netgrip.engine.agent import Deps, node_context, run_node
from netgrip.engine.clock import FakeClock
from netgrip.evidence.service import EvidenceService
from netgrip.store.projections import append_and_project
from netgrip.store.settings import DEFAULT_SETTINGS, SettingsModel, resolve_investigation_settings

INV = "inv-1"
OTHER = "inv-2"
NASA = "https://example.org/nasa/great-wall-from-orbit"
MYTH = "https://example.org/history/wall-myth"  # two timeouts, then ok on the third route


def ev(type, data, node_id=None, actor="orchestrator"):
    return EventDraft(type=type, actor=actor, node_id=node_id, data=data)


def proposed(disp, kind="Divergent", parent=None, depth=1, question="Is the Wall visible?"):
    return {"display_id": disp, "parent_id": parent, "kind": kind, "question": question,
            "depends_on": [], "depth": depth, "proposed_by": "orchestrator"}  # fmt: skip


def created(inv=INV):
    g = SettingsModel.model_validate(DEFAULT_SETTINGS)
    settings = resolve_investigation_settings(g, {"effort": "Medium"})
    return ev("investigation.created", {"prompt": "p", "settings": settings}, actor="user")


async def seed(engine, inv=INV):
    """Root n-r (a coordinator marked waiting, never started) with D1 n-1 and D1a n-1a."""
    await append_and_project(engine.db, inv, [
        created(inv),
        ev("investigation.root_goal_set", {"root_goal": "Is the Great Wall visible?"}),
        ev("node.proposed", proposed("R", "Root", depth=0), node_id="n-r"),
        ev("node.proposed", proposed("D1", parent="n-r"), node_id="n-1"),
        ev("node.proposed", {**proposed("D1a", parent="n-1", depth=2, question="Which lens?"),
                             "proposed_by": "n-1"}, node_id="n-1a"),
        ev("node.approved", {"budget": {"sources": 3, "child_nodes": 2}}, node_id="n-r"),
        ev("node.approved", {"budget": {"sources": 3, "child_nodes": 2}}, node_id="n-1"),
        ev("node.approved", {"budget": {"sources": 2, "child_nodes": 0}}, node_id="n-1a"),
        ev("node.waiting_on_children", {}, node_id="n-r"),
    ], engine.bus)  # fmt: skip


def decide(action, **kw):
    return {"parsed": {"action": action, **kw}}


def conclude(text="It is hard to see", **kw):
    return decide("conclude", verdict={"text": text, "confidence": "medium"},
                  open_questions=["Which lens was used?"], **kw)  # fmt: skip


def extraction(*claims):
    found = [{"text": c, "stance": "supports"} for c in claims]
    return {"parsed": {"claims": found, "credibility": "Primary", "published_at": None,
                       "origin": "nasa.gov"}}  # fmt: skip


UNRELATED = {"parsed": {"relation": "unrelated", "claim_id": None}}


def deps_for(engine, script, url=NASA):
    return Deps(
        db=engine.db,
        model=FakeModelClient({"evidence.match": [UNRELATED], **script}),
        search=FakeSearch({"default": [{"url": url, "title": "t", "snippet": "s"}]}),
        fetcher=FakeFetcher.from_scenario("great_wall_web"),
        pages=engine.pages,
        evidence=EvidenceService(engine.db, engine.bus),
        clock=FakeClock(),
        bus=engine.bus,
    )


async def run_d1(engine, url=NASA, inv=INV):
    deps = deps_for(engine, {
        "node.decide": [decide("search", query="visible from orbit"), conclude()],
        "node.extract": [extraction("Astronauts could not see the Wall unaided")],
    }, url)  # fmt: skip
    ctx = await node_context(deps, inv, "n-1")
    await run_node(ctx)
    return ctx


async def detail(client, node_id, inv=INV):
    r = await client.get(f"/api/investigations/{inv}/nodes/{node_id}")
    assert r.status_code == 200, r.text
    return r.json()


async def test_node_detail_has_brief_as_received(app_client):
    engine = app_client.app.state.engine
    await seed(engine)
    await run_d1(engine)
    d = await detail(app_client, "n-1")
    [started] = await engine.db.read(
        "SELECT data FROM events WHERE type = 'node.started' AND node_id = 'n-1'"
    )
    assert d["brief"] == json.loads(started["data"])["brief"]
    assert d["brief"]["root_goal"] == "Is the Great Wall visible?"
    assert d["node"]["display_id"] == "D1" and d["node"]["status"] == "Completed"
    assert d["open_questions"] == ["Which lens was used?"]
    [claim] = d["claims"]
    assert claim["text"] == "Astronauts could not see the Wall unaided"
    [src] = claim["supporting"]
    assert src["url"] == NASA and src["credibility"] == "Primary" and src["page_version_id"]
    assert claim["contradicting"] == []
    assert d["proposals"] == [{"node_id": "n-1a", "display_id": "D1a", "question": "Which lens?",
                               "decision": "approved", "reason": None}]  # fmt: skip
    assert d["branch"]["nodes"] == 1 and d["branch"]["nodes_max"] == 2
    assert d["branch"]["depth"] == 2 and d["branch"]["depth_max"] == 4
    assert d["branch"]["reach"] == 1  # D1 is done; D1a is still Pending
    assert d["branch"]["spent_usd"] > 0

    # The root became a coordinator from the plan: it never started, so it has no brief yet.
    root = await detail(app_client, "n-r")
    assert root["brief"] is None and root["trail"] == [] and root["open_questions"] == []
    assert (await app_client.get(f"/api/investigations/{INV}/nodes/nope")).status_code == 404


async def test_trail_lists_steps_with_routes_and_retries(app_client):
    engine = app_client.app.state.engine
    await seed(engine)
    await run_d1(engine, url=MYTH)
    await append_and_project(engine.db, INV, [
        ev("instruction.queued", {"instruction_id": "i-1", "text": "Prefer NASA"}, "n-1", "user"),
        ev("instruction.applied", {"instruction_id": "i-1", "diff": {}}, "n-1"),
    ])  # fmt: skip
    trail = (await detail(app_client, "n-1"))["trail"]
    rows = [(t["step"], t["activity"], t["kind"], t["route"]) for t in trail]
    assert rows == [
        (1, "Planning", "decision", "search"),
        (2, "Searching", "search", None),
        (3, "Reading", None, None),
        (4, "Retrying", None, "browser"),
        (5, "Retrying", "fetch", "hardened"),
        (6, "Extracting", "extraction", None),
        (7, "Reasoning", "decision", "conclude"),
        (8, None, "conclusion", None),
    ]
    assert [t["retry"] for t in trail[3:5]] == [{"n": 2, "m": 3}, {"n": 3, "m": 3}]
    assert trail[2]["detail"] == MYTH and trail[1]["detail"] == "visible from orbit"
    page = trail[4]["page_version_id"]
    assert page and trail[5]["page_version_id"] == page
    assert all(t["started_at"] and t["ended_at"] for t in trail)
    assert trail[2]["ended_at"] == trail[3]["started_at"]
    assert [t["instruction_applied"] for t in trail] == [[]] * 7 + [["i-1"]]


async def test_inherited_instructions_ordered_root_down(app_client):
    engine = app_client.app.state.engine
    await seed(engine)
    await append_and_project(engine.db, INV, [
        ev("instruction.queued", {"instruction_id": "i-d1", "text": "on D1"}, "n-1", "user"),
        ev("instruction.queued", {"instruction_id": "i-own", "text": "on D1a"}, "n-1a", "user"),
        ev("instruction.queued", {"instruction_id": "i-r", "text": "on R"}, "n-r", "user"),
        ev("instruction.applied", {"instruction_id": "i-r", "diff": {}}, "n-r"),
    ])  # fmt: skip
    ins = (await detail(app_client, "n-1a"))["instructions"]
    assert [(i["id"], i["from_display_id"]) for i in ins["inherited"]] == [
        ("i-r", "R"),
        ("i-d1", "D1"),
    ]
    assert ins["inherited"][0]["state"] == "applied" and ins["inherited"][1]["state"] == "queued"
    assert [i["id"] for i in ins["own"]] == ["i-own"]
    assert ins["own"][0]["text"] == "on D1a"


async def test_page_text_only_for_own_investigation(app_client):
    engine = app_client.app.state.engine
    await seed(engine)
    await append_and_project(engine.db, OTHER, [created(OTHER)])
    await run_d1(engine)
    [step] = [t for t in (await detail(app_client, "n-1"))["trail"] if t["kind"] == "fetch"]
    pv = step["page_version_id"]
    r = await app_client.get(f"/api/investigations/{INV}/pages/{pv}")
    assert r.status_code == 200
    page = r.json()
    assert set(page) == {"url", "title", "fetched_at", "text"}
    assert page["url"] == NASA and page["text"] and page["fetched_at"]
    assert (await app_client.get(f"/api/investigations/{OTHER}/pages/{pv}")).status_code == 404
    assert (await app_client.get(f"/api/investigations/{INV}/pages/nope")).status_code == 404
    assert (await app_client.get(f"/api/investigations/nope/pages/{pv}")).status_code == 404


async def test_ephemeral_text_streamed_but_not_stored(app_client):
    engine = app_client.app.state.engine
    await seed(engine)
    sub = engine.bus.subscribe(INV)
    await run_d1(engine)
    seen: list[Ephemeral] = []
    while not sub._queue.empty():
        item = sub._queue.get_nowait()
        if isinstance(item, Ephemeral):
            seen.append(item)
    sub.close()
    assert seen and all(e.kind == "model_text" and e.node_id == "n-1" for e in seen)
    assert all(set(e.data) == {"step", "delta"} for e in seen)
    by_step: dict[int, str] = {}
    for e in seen:
        by_step[e.data["step"]] = by_step.get(e.data["step"], "") + e.data["delta"]
    trail = (await detail(app_client, "n-1"))["trail"]
    decided = {t["step"] for t in trail if t["activity"] in ("Planning", "Reasoning")}
    assert set(by_step) == decided
    assert len([e for e in seen if e.data["step"] == 1]) > 1  # deltas, not one block
    assert json.loads(by_step[1])["action"] == "search"
    # Nothing of it is in the log.
    rows = await engine.db.read("SELECT type, data FROM events WHERE investigation_id = ?", [INV])
    assert not any("model_text" in r["type"] or by_step[1] in r["data"] for r in rows)
    assert not any('"delta"' in r["data"] for r in rows)


async def test_events_filter_and_page_backwards(app_client):
    engine = app_client.app.state.engine
    await seed(engine)  # 9 events
    await append_and_project(engine.db, INV, [
        ev("node.activity", {"activity": "Planning", "step": "plan"}, "n-1", "node"),
        ev("instruction.queued", {"instruction_id": "i-1", "text": "x"}, "n-1", "user"),
    ] + [ev("investigation.state_changed", {"from": "Draft", "to": "Draft", "origin": "system"},
            actor="system") for _ in range(205)])  # fmt: skip
    base = f"/api/investigations/{INV}/events"
    page = (await app_client.get(f"{base}?before=10&limit=3")).json()
    assert [e["seq"] for e in page] == [7, 8, 9]
    page = (await app_client.get(f"{base}?before=4")).json()
    assert [e["seq"] for e in page] == [1, 2, 3]
    users = (await app_client.get(f"{base}?actor=user")).json()
    assert [(e["seq"], e["type"]) for e in users] == [(1, "investigation.created"),
                                                      (11, "instruction.queued")]  # fmt: skip
    mine = (await app_client.get(f"{base}?node_id=n-1")).json()
    assert [e["seq"] for e in mine] == [4, 7, 10, 11]
    typed = (await app_client.get(f"{base}?types=node.approved,node.activity&before=10")).json()
    assert [e["seq"] for e in typed] == [6, 7, 8]
    both = (await app_client.get(f"{base}?actor=node,user&node_id=n-1")).json()
    assert [e["seq"] for e in both] == [10, 11]
    after = (await app_client.get(f"{base}?after=214&limit=5")).json()
    assert [e["seq"] for e in after] == [215, 216]

    snap = (await app_client.get(f"/api/investigations/{INV}")).json()
    recent = snap["recent_events"]
    assert len(recent) == 200 and recent[-1]["seq"] == snap["seq"] == 216
    assert [e["seq"] for e in recent] == list(range(17, 217))


@pytest.mark.parametrize("bad", ["before=0", "actor=robot", "limit=0"])
async def test_events_query_rejects_bad_parameters(app_client, bad):
    engine = app_client.app.state.engine
    await seed(engine)
    r = await app_client.get(f"/api/investigations/{INV}/events?{bad}")
    assert r.status_code == 422


async def test_outage_retry_has_no_fetch_route(app_client):
    engine = app_client.app.state.engine
    await seed(engine)
    retry = {"activity": "Retrying", "step": "plan", "retry": {"n": 2, "m": 5},
             "detail": "fake: unavailable"}  # fmt: skip
    await append_and_project(engine.db, INV, [
        ev("node.activity", {"activity": "Planning", "step": "plan"}, "n-1", "node"),
        ev("node.activity", retry, "n-1", "orchestrator"),
        ev("node.activity", {**retry, "step": "search", "retry": {"n": 3, "m": 5}}, "n-1"),
    ])  # fmt: skip
    trail = (await detail(app_client, "n-1"))["trail"]
    assert [(t["activity"], t["retry"], t["route"]) for t in trail] == [
        ("Planning", None, None),
        ("Retrying", {"n": 2, "m": 5}, None),
        ("Retrying", {"n": 3, "m": 5}, None),
    ]
