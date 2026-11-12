import json

import pytest

from netgrip.adapters.fakes import FakeFetcher, FakeModelClient, FakeSearch
from netgrip.boundary.events import EventDraft
from netgrip.engine.agent import Deps, node_context, run_node
from netgrip.engine.brief import build_brief
from netgrip.engine.clock import FakeClock
from netgrip.engine.orchestrator import (
    OrchestratorContext,
    decide_next,
    on_node_failed,
    on_node_returned,
    review_proposals,
    synthesis_claims,
)
from netgrip.evidence.service import EvidenceService
from netgrip.store.db import open_db
from netgrip.store.pages import PageStore
from netgrip.store.projections import append_and_project
from netgrip.store.settings import DEFAULT_SETTINGS, SettingsModel, resolve_investigation_settings

INV = "inv-1"
PAGE = "https://example.org/secret-page"
SENTINEL = "ZEBRA-QUOKKA-SENTINEL page body that must never reach the orchestrator"


def ev(type, data, node_id=None, actor="orchestrator"):
    return EventDraft(type=type, actor=actor, node_id=node_id, data=data)


def proposed(disp, kind="Divergent", parent=None, depth=1, question="Is the Wall visible?",
             justification="Needed for the goal"):  # fmt: skip
    return {"display_id": disp, "parent_id": parent, "kind": kind, "question": question,
            "justification": justification, "depends_on": [], "depth": depth,
            "proposed_by": "orchestrator"}  # fmt: skip


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    g = SettingsModel.model_validate(DEFAULT_SETTINGS)
    settings = resolve_investigation_settings(g, {"effort": "Medium"})
    await append_and_project(
        d, INV,
        [
            ev("investigation.created", {"prompt": "p", "settings": settings}, actor="user"),
            ev("investigation.root_goal_set", {"root_goal": "Is the Great Wall visible?"}),
            ev("node.proposed", proposed("R", "Synthesis", depth=0), node_id="n-r"),
            ev("node.proposed", proposed("D1", parent="n-r"), node_id="n-1"),
            ev("node.approved", {"budget": {"sources": 3, "child_nodes": 2}}, node_id="n-r"),
            ev("node.approved", {"budget": {"sources": 3, "child_nodes": 3}}, node_id="n-1"),
        ],
    )  # fmt: skip
    yield d
    await d.close()


def octx(db, script, repeat_last=False):
    return OrchestratorContext(
        investigation_id=INV,
        db=db,
        model=FakeModelClient(script, repeat_last=repeat_last),
        evidence=EvidenceService(db),
        clock=FakeClock(),
    )


async def propose_children(db, n, parent="n-1", start=1):
    ids = [f"c-{i}" for i in range(start, start + n)]
    await append_and_project(db, INV, [
        ev("node.proposed", proposed(f"D1{chr(96 + i)}" if i <= 26 else f"D1z{i}", parent=parent,
                                     depth=2, question=f"Sub-question {i}"),
           node_id=nid, actor="node")
        for i, nid in zip(range(start, start + n), ids, strict=True)
    ])  # fmt: skip
    return ids


async def rows(db):
    r = await db.read("SELECT * FROM nodes WHERE investigation_id = ? ORDER BY seq", [INV])
    return {x["id"]: x for x in r}


async def events(db, type):
    r = await db.read(
        "SELECT node_id, data FROM events WHERE investigation_id = ? AND type = ? ORDER BY seq",
        [INV, type],
    )
    return [(x["node_id"], json.loads(x["data"])) for x in r]


async def exhaust(db):
    async with db.tx() as tx:
        await tx.execute(
            "UPDATE investigations SET spent_usd = spending_limit_usd WHERE id = ?", [INV]
        )


def approve_all(_ids=None):
    return {"parsed": {"decisions": []}}  # no objection: every candidate passes


async def test_excess_children_rejected_for_budget_and_remain_visible(db):
    ids = await propose_children(db, 30)
    ctx = octx(db, {"orchestrator.review": [approve_all()]})
    decisions = await review_proposals(ctx, ids)
    approved = [d for d in decisions if d.approve]
    rejected = [d for d in decisions if not d.approve]
    assert [d.node_id for d in approved] == ids[:3]
    assert len(rejected) == 27 and all(d.reason == "budget" for d in rejected)
    nodes = await rows(db)
    assert all(nodes[i]["status"] == "Rejected" for i in ids[3:])  # kept, visible (G5)
    assert all(nodes[i]["status"] == "Pending" for i in ids[:3])
    rej = await events(db, "node.rejected")
    assert len(rej) == 27 and all(d == {"reason": "budget", "duplicate_of": None} for _, d in rej)
    # The reviewer saw only the three candidates that passed the code rules.
    review = [c for c in ctx.model.calls if c.purpose == "orchestrator.review"]
    assert len(review) == 1 and review[0].tier == "strong"
    assert "Sub-question 4" not in review[0].messages[0].content


async def test_too_deep_rejected_for_budget(db):
    await append_and_project(db, INV, [
        ev("node.proposed", proposed("X", parent="n-1", depth=5), node_id="deep", actor="node")
    ])  # fmt: skip
    ctx = octx(db, {})
    [d] = await review_proposals(ctx, ["deep"])
    assert (d.approve, d.reason) == (False, "budget")
    assert ctx.model.calls == []  # nothing left to review: no model call


async def test_weak_justification_rejected_with_reason(db):
    ids = await propose_children(db, 2)
    ctx = octx(db, {"orchestrator.review": [{"parsed": {"decisions": [
        {"display_id": "D1b", "approve": False, "reason": "weak justification: restates parent",
         "duplicate_of": None},
    ]}}]})  # fmt: skip
    decisions = {d.node_id: d for d in await review_proposals(ctx, ids)}
    assert decisions[ids[0]].approve
    assert not decisions[ids[1]].approve
    assert decisions[ids[1]].reason == "weak justification: restates parent"
    nodes = await rows(db)
    assert nodes[ids[1]]["status"] == "Rejected"
    assert nodes[ids[1]]["rejection_reason"] == "weak justification: restates parent"


async def test_duplicate_rejected_with_link(db):
    ids = await propose_children(db, 1)
    ctx = octx(db, {"orchestrator.review": [{"parsed": {"decisions": [
        {"display_id": "D1a", "approve": False, "reason": "same question as D1",
         "duplicate_of": "D1"},
    ]}}]})  # fmt: skip
    [d] = await review_proposals(ctx, ids)
    assert (d.approve, d.reason, d.duplicate_of) == (False, "duplicate", "n-1")
    assert (await events(db, "node.rejected"))[-1] == (
        ids[0],
        {"reason": "duplicate", "duplicate_of": "n-1"},
    )
    assert (await rows(db))[ids[0]]["duplicate_of"] == "n-1"
    spend = await events(db, "spend.recorded")
    assert spend and spend[-1][0] is None  # orchestrator spend, not a node's


async def _run_node_reading_page(db, tmp_path):
    fetch = FakeFetcher({PAGE: {"text": SENTINEL, "title": "Secret"}})
    deps = Deps(
        db=db,
        model=FakeModelClient(
            {
                "evidence.match": [{"parsed": {"relation": "unrelated", "claim_id": None}}],
                "node.decide": [
                    {"parsed": {"action": "search", "query": "wall"}},
                    {
                        "parsed": {
                            "action": "conclude",
                            "verdict": {"text": "Not visible unaided", "confidence": "medium"},
                            "open_questions": [],
                        }
                    },
                ],
                "node.extract": [
                    {
                        "parsed": {
                            "claims": [{"text": "The Wall is narrow", "stance": "supports"}],
                            "credibility": "Primary",
                            "published_at": None,
                            "origin": "example.org",
                        }
                    }
                ],
            }
        ),  # fmt: skip
        search=FakeSearch({"default": [{"url": PAGE, "title": "t", "snippet": "s"}]}),
        fetcher=fetch,
        pages=PageStore(db, tmp_path / "data"),
        evidence=EvidenceService(db),
        clock=FakeClock(),
    )
    ctx = await node_context(deps, INV, "n-1")
    await run_node(ctx)
    assert (await rows(db))["n-1"]["status"] == "Completed"
    assert any(SENTINEL in (m.content or "") for c in deps.model.calls for m in c.messages)


async def test_orchestrator_never_receives_page_text(db, tmp_path):
    await _run_node_reading_page(db, tmp_path)
    ids = await propose_children(db, 1, parent="n-r")
    ctx = octx(
        db,
        {
            "node.relevance": [{"parsed": {"relevant": True, "reason": "on goal"}}],
            "orchestrator.review": [approve_all()],
            "orchestrator.next": [{"parsed": {"decision": "conclude", "verify": []}}],
        },
    )
    await on_node_returned(ctx, "n-1")
    await review_proposals(ctx, ids)
    await decide_next(ctx)
    assert {c.purpose for c in ctx.model.calls} == {
        "node.relevance",
        "orchestrator.review",
        "orchestrator.next",
    }
    for c in ctx.model.calls:
        assert c.tools is None
        blob = c.system + "".join(m.content or "" for m in c.messages)
        assert "ZEBRA-QUOKKA" not in blob
    # The verdict is what the orchestrator does see.
    nxt = next(c for c in ctx.model.calls if c.purpose == "orchestrator.next")
    assert "Not visible unaided" in nxt.messages[0].content


async def test_off_topic_result_flagged(db, tmp_path):
    await _run_node_reading_page(db, tmp_path)
    ctx = octx(db, {"node.relevance": [{"parsed": {"relevant": False, "reason": "about walls"}}]})
    assert await on_node_returned(ctx, "n-1") is True
    [call] = ctx.model.calls
    assert (call.purpose, call.tier) == ("node.relevance", "fast")
    assert (await rows(db))["n-1"]["off_topic"] == 1
    [(nid, data)] = await events(db, "node.off_topic")
    assert nid == "n-1" and data["reason"] == "about walls"
    # node.completed keeps its overview shape; the claims stay stored but out of synthesis.
    claims = await db.read("SELECT id FROM claims WHERE investigation_id = ?", [INV])
    assert claims
    assert await synthesis_claims(db, INV) == []


async def test_on_topic_result_kept_for_synthesis(db, tmp_path):
    await _run_node_reading_page(db, tmp_path)
    ctx = octx(db, {"node.relevance": [{"parsed": {"relevant": True, "reason": "ok"}}]})
    assert await on_node_returned(ctx, "n-1") is False
    assert [c.text for c in await synthesis_claims(db, INV)] == ["The Wall is narrow"]


async def test_failed_node_retried_once_then_stays_failed(db):
    fail = ev("node.failed", {"reason": "no usable source"}, node_id="n-1", actor="node")
    await append_and_project(db, INV, [fail])
    ctx = octx(db, {})
    assert await on_node_failed(ctx, "n-1") is True
    [(nid, data)] = await events(db, "node.reset")
    assert nid == "n-1" and data["reason"] == "auto_retry"
    assert "different approach" in data["hint"] and "no usable source" in data["hint"]
    assert (await rows(db))["n-1"]["status"] == "Pending"
    brief = await build_brief(db, "n-1")
    assert brief.task.hint == data["hint"]

    await append_and_project(db, INV, [fail])
    assert await on_node_failed(ctx, "n-1") is False
    assert len(await events(db, "node.reset")) == 1
    assert (await rows(db))["n-1"]["status"] == "Failed"
    assert ctx.model.calls == []


async def test_failed_node_not_retried_without_budget(db):
    await exhaust(db)
    await append_and_project(db, INV, [ev("node.failed", {"reason": "x"}, node_id="n-1")])
    assert await on_node_failed(octx(db, {}), "n-1") is False
    assert (await rows(db))["n-1"]["status"] == "Failed"


async def test_budget_exhausted_concludes_and_marks_cut_short(db):
    await exhaust(db)
    ctx = octx(db, {})
    assert await decide_next(ctx) == "conclude"
    assert ctx.model.calls == []  # no model call once the budget is gone
    [(_, data)] = await events(db, "investigation.concluding")
    assert data == {"cut_short_by": "budget"}
    inv = (await db.read("SELECT cut_short_by FROM investigations WHERE id = ?", [INV]))[0]
    assert inv["cut_short_by"] == "budget"


async def test_decide_next_proposes_verification_nodes(db, tmp_path):
    await _run_node_reading_page(db, tmp_path)
    [claim] = await db.read("SELECT id FROM claims WHERE investigation_id = ?", [INV])
    ctx = octx(db, {"orchestrator.next": [{"parsed": {"decision": "continue", "verify": [
        {"claim_id": claim["id"], "question": "Is the Wall really narrow?",
         "justification": "key claim, one source"}]}}]})  # fmt: skip
    assert await decide_next(ctx) == "continue"
    assert ctx.model.calls[0].tier == "strong"
    v = [n for n in (await rows(db)).values() if n["kind"] == "Verification"]
    assert len(v) == 1 and v[0]["display_id"] == "V1" and v[0]["status"] == "Pending"
    assert json.loads(v[0]["budget"])["tier"] == "verifier"
    assert await events(db, "investigation.concluding") == []


async def test_decide_next_conclude_not_cut_short(db):
    ctx = octx(db, {"orchestrator.next": [{"parsed": {"decision": "conclude", "verify": []}}]})
    assert await decide_next(ctx) == "conclude"
    [(_, data)] = await events(db, "investigation.concluding")
    assert data == {"cut_short_by": None}


async def test_malformed_review_entries_fall_back_to_approval(db):
    ids = await propose_children(db, 1)
    bad = {"parsed": {"decisions": [{"display_id": "D1a", "approve": "no"}]}}
    ctx = octx(db, {"orchestrator.review": [bad, bad, bad]})
    [d] = await review_proposals(ctx, ids)
    assert d.approve
    assert len(ctx.model.calls) == 3
