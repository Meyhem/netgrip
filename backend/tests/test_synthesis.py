"""Synthesis: the report is written from the evidence store and checked in code (Phase 8)."""

import asyncio
import uuid

import pytest
from test_runtime import INV, ev, events, make_engine, proposed, seed, state

from netgrip.adapters.fakes import FakeModelClient
from netgrip.boundary.commands import Command
from netgrip.engine.synthesis import build_limits, gather_evidence, synthesise
from netgrip.report.model import CANNOT_ANSWER, Report
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def cmd(type, **payload):
    return Command(id=uuid.uuid4(), type=type, investigation_id=INV, payload=payload)


def stmt(text, *ids, premise=None):
    return {"text": text, "claim_ids": list(ids), "premise": premise}


def written(answer=None, wrong=(), findings=(), unverified=(), confidence="medium"):
    return {"parsed": {"answer": list(answer or [stmt("Answer.", "c1")]), "wrong": list(wrong),
                       "findings": list(findings), "unverified": list(unverified),
                       "answer_confidence": confidence}}  # fmt: skip


def client(*entries):
    return FakeModelClient({"synthesis.write": list(entries or [written()])})


async def add_source(db, sid="s1", node="n-1", published_at="2005-02-01", cred="Primary"):
    await append_and_project(db, INV, [ev(
        "source.recorded",
        {"source_id": sid, "url": f"https://example.org/{sid}", "title": sid,
         "page_version_id": f"pv-{sid}", "credibility": cred, "published_at": published_at,
         "origin_key": sid}, node_id=node, actor="node")])  # fmt: skip


async def add_claim(db, cid, node="n-1", text=None, status="Confirmed", source="s1"):
    await append_and_project(db, INV, [ev(
        "claim.added",
        {"claim_id": cid, "text": text or f"Claim text {cid}", "status": status,
         "supporting": [source], "contradicting": []}, node_id=node, actor="node")])  # fmt: skip


async def reports(db):
    return await db.read("SELECT * FROM reports WHERE investigation_id = ?", [INV])


async def stored(db) -> Report:
    [row] = await reports(db)
    return Report.model_validate_json(row["body"])


async def seeded(db, tmp_path, model, nodes=None, claims=("c-1",)):
    await seed(db, nodes or [("n-1", proposed("D1")), ("n-2", proposed("D2"))])
    await add_source(db)
    for i, cid in enumerate(claims):
        await add_claim(db, cid, node="n-1" if i == 0 else "n-2")
    return make_engine(db, tmp_path, model)


def ids_of(report: Report, key: str) -> list[list[str]]:
    return [s.claim_ids for s in report.section(key).statements]


async def test_report_built_from_evidence_not_summaries(db, tmp_path):
    model = client(written([stmt("Answer.", "c1")]))
    engine = await seeded(db, tmp_path, model, claims=("c-1",))
    await append_and_project(db, INV, [ev("node.completed", {
        "verdict": {"text": "SECRET VERDICT TEXT", "confidence": "high"}, "open_questions": [],
    }, node_id="n-1")])  # fmt: skip
    await synthesise(engine, INV)
    prompt = "\n".join(m.content for m in model.calls[0].messages)
    assert "Claim text c-1" in prompt and "SECRET VERDICT TEXT" not in prompt
    assert "2005-02-01" in prompt  # the source's publication date (V5)
    report = await stored(db)
    assert ids_of(report, "answer") == [["c-1"]]  # the handle is mapped to the real id
    assert await state(db) == "Completed"
    root = await db.read("SELECT status, verdict FROM nodes WHERE id = 'n-r'")
    assert root[0]["status"] == "Completed"  # synthesis completes the root


async def test_ignored_branch_claims_absent_and_branch_listed_in_limits(db, tmp_path):
    model = client(written([stmt("Answer.", "c1")]))
    engine = await seeded(db, tmp_path, model, claims=("c-1", "c-2"))
    await append_and_project(db, INV, [ev("node.inclusion_changed", {
        "node_ids": ["n-2"], "inclusion": "Ignored", "by": "user", "instruction_id": None,
    }, actor="user")])  # fmt: skip
    await synthesise(engine, INV)
    prompt = model.calls[0].messages[0].content
    assert "Claim text c-1" in prompt and "Claim text c-2" not in prompt
    report = await stored(db)
    [branch] = report.limits.excluded_branches
    assert (branch.display_id, branch.by) == ("D2", "user")


async def test_refuted_premise_appears_in_where_you_were_wrong(db, tmp_path):
    nodes = [("n-1", proposed("P1", "Premise check"))]
    model = client(written(wrong=[stmt("You assumed X; it is not so.", "c1", premise="P1")]))
    engine = await seeded(db, tmp_path, model, nodes=nodes)
    await append_and_project(db, INV, [
        ev("premise.extracted", {"premise_id": "pr-1", "text": "X holds", "node_id": "n-1"}),
        ev("premise.outcome", {"premise_id": "pr-1", "outcome": "refuted"}, node_id="n-1"),
    ])  # fmt: skip
    await synthesise(engine, INV)
    report = await stored(db)
    assert [s.key for s in report.sections] == [
        "answer", "wrong", "findings", "unverified", "limits"]  # fmt: skip
    assert report.section("wrong").statements[0].premise_node_id == "n-1"
    assert "P1: X holds -> refuted" in model.calls[0].messages[0].content


async def test_no_wrong_section_without_refuted_premise(db, tmp_path):
    model = client(written(wrong=[stmt("Not needed.", "c1")]))
    engine = await seeded(db, tmp_path, model)
    await synthesise(engine, INV)
    report = await stored(db)
    assert report.section("wrong") is None
    assert [s.key for s in report.sections] == ["answer", "findings", "unverified", "limits"]


async def test_below_confirmed_statements_are_hedged(db, tmp_path):
    model = client(written([stmt("Reportedly so.", "c1"), stmt("Sure.", "c2")]))
    engine = await seeded(db, tmp_path, model, claims=("c-1", "c-2"))
    await append_and_project(db, INV, [ev("claim.updated", {
        "claim_id": "c-1", "status": "Supported", "supporting": ["s1"], "contradicting": [],
    }, node_id="n-1", actor="node")])  # fmt: skip
    await synthesise(engine, INV)
    first, second = (await stored(db)).section("answer").statements
    assert first.hedged is True and second.hedged is False


async def test_uncited_statement_never_stored(db, tmp_path):
    bad = written([stmt("No citation at all."), stmt("Cited.", "c1")])
    model = client(bad, bad, bad)
    engine = await seeded(db, tmp_path, model)
    await synthesise(engine, INV)
    assert len(model.calls) == 3  # first call and two retries
    report = await stored(db)
    assert [s.text for s in report.section("answer").statements] == ["Cited."]
    assert "cites no claim" in model.calls[1].messages[0].content  # the errors are listed


async def test_unknown_claim_id_retried_then_dropped(db, tmp_path):
    good = written([stmt("Fine.", "c1")])
    model = client(written([stmt("Ghost.", "c9")]), good)
    engine = await seeded(db, tmp_path, model)
    await synthesise(engine, INV)
    assert len(model.calls) == 2
    assert [s.text for s in (await stored(db)).section("answer").statements] == ["Fine."]

    ghost = written([stmt("Ghost.", "c9")])
    model = client(ghost, ghost, ghost)
    engine = await seeded_again(db, tmp_path, model)
    await synthesise(engine, INV)
    report = await stored(db)
    assert [s.text for s in report.section("answer").statements] == [CANNOT_ANSWER]
    assert report.answer_confidence == "low"


async def seeded_again(db, tmp_path, model):
    """The same investigation written again: a fresh synthesis replaces the report (D-16)."""
    await append_and_project(db, INV, [ev("investigation.state_changed", {
        "from": "Completed", "to": "Synthesising", "origin": "user"}, actor="user")])  # fmt: skip
    return make_engine(db, tmp_path, model)


async def test_no_claims_writes_cannot_answer_without_model_call(db, tmp_path):
    model = client()
    await seed(db, [("n-1", proposed("D1"))])
    await synthesise(make_engine(db, tmp_path, model), INV)
    assert model.calls == []
    report = await stored(db)
    assert [s.text for s in report.section("answer").statements] == [CANNOT_ANSWER]
    assert report.answer_confidence == "low"
    assert await state(db) == "Completed"


async def test_finish_now_marks_ended_early_in_limits(db, tmp_path):
    model = client()
    engine = await seeded(db, tmp_path, model)
    await engine.submit(cmd("finish_now"))
    await asyncio.gather(*engine._background)
    report = await stored(db)
    assert report.limits.ended_early and report.limits.cut_short_by == "finish_now"
    [(_, _, created)] = await events(db, "report.created")
    assert created["ended_early"] is True and created["cut_short_by"] == "finish_now"


async def test_budget_cut_short_stated(db, tmp_path):
    engine = await seeded(db, tmp_path, client())
    await append_and_project(db, INV, [ev("investigation.concluding", {"cut_short_by": "budget"})])
    await synthesise(engine, INV)
    report = await stored(db)
    assert report.limits.cut_short_by == "budget" and not report.limits.ended_early
    assert any("cut short" in s.text for s in report.section("limits").statements)


async def test_limits_state_effort_and_threshold(db, tmp_path):
    engine = await seeded(db, tmp_path, client())
    await synthesise(engine, INV)
    report = await stored(db)
    assert (report.limits.effort, report.limits.confirm_threshold) == ("Medium", 2)
    assert "Effort: Medium" in report.section("limits").statements[0].text
    assert "2 independent sources" in report.section("limits").statements[0].text


async def test_unobtainable_pages_listed(db, tmp_path):
    engine = await seeded(db, tmp_path, client())
    for _ in range(2):  # the same page twice is listed once
        await append_and_project(
            db,
            INV,
            [
                ev(
                    "page.unobtainable",
                    {"url": "https://example.org/blocked", "attempts": []},
                    node_id="n-1",
                    actor="node",
                )
            ],
        )
    await synthesise(engine, INV)
    assert (await stored(db)).limits.unobtainable_pages == ["https://example.org/blocked"]


async def test_narrowing_instructions_listed(db, tmp_path):
    await seeded(db, tmp_path, client())
    await append_and_project(db, INV, [
        ev("instruction.queued", {"instruction_id": "i-1", "text": "Only primary sources."},
           node_id="n-1", actor="user"),
        ev("instruction.applied", {"instruction_id": "i-1", "at_step": 1,
                                   "diff": {"kept": [], "superseded": [], "proposed": [],
                                            "notes": []}}, node_id="n-1"),
    ])  # fmt: skip
    limits = await build_limits(db, INV)
    assert [(i.text, i.node_display_id) for i in limits.instructions] == [
        ("Only primary sources.", "D1")]  # fmt: skip


async def test_stopped_can_be_finished_into_report(db, tmp_path):
    engine = await seeded(db, tmp_path, client())
    await engine.submit(cmd("stop"))
    assert await state(db) == "Stopped"
    await engine.submit(cmd("finish_now"))
    await asyncio.gather(*engine._background)
    assert await state(db) == "Completed"
    assert (await stored(db)).limits.ended_early


async def test_kill_during_synthesis_yields_one_report(db, tmp_path):
    entered = asyncio.Event()

    class Hanging(FakeModelClient):
        async def complete(self, req):
            entered.set()
            await asyncio.Event().wait()

    engine = await seeded(db, tmp_path, Hanging({}))
    task = asyncio.create_task(synthesise(engine, INV))
    await entered.wait()
    task.cancel()  # the process dies mid-call
    await asyncio.gather(task, return_exceptions=True)
    assert await state(db) == "Synthesising" and await reports(db) == []
    # The restart finds it Synthesising and writes the report again.
    engine = make_engine(db, tmp_path, client())
    await engine.start()
    await asyncio.gather(*engine._background)
    assert len(await reports(db)) == 1 and len(await events(db, "report.created")) == 1
    assert await state(db) == "Completed"


async def test_synthesis_spend_recorded_and_respects_limit(db, tmp_path):
    engine = await seeded(db, tmp_path, client())
    await synthesise(engine, INV)
    assert (await db.read("SELECT spent_usd FROM investigations"))[0]["spent_usd"] == 0.01
    assert (await stored(db)).totals.spent_usd == 0.01

    # At the limit: Paused with the cause, no report, back to Synthesising on resume.
    model = client()
    await seed(db, [("m-1", proposed("D1"))], inv="inv-2", root="m-r")
    await append_and_project(db, "inv-2", [
        ev("source.recorded", {"source_id": "t1", "url": "https://e.org/t", "title": None,
                               "page_version_id": "pv", "credibility": "Primary",
                               "published_at": None, "origin_key": "t"}, node_id="m-1"),
        ev("claim.added", {"claim_id": "k-1", "text": "K", "status": "Confirmed",
                           "supporting": ["t1"], "contradicting": []}, node_id="m-1"),
        ev("spend.recorded", {"tier": "strong", "model": "m", "amount_usd": "5.0",
                              "approximate": False, "tokens_in": 1, "tokens_out": 1}),
    ])  # fmt: skip
    engine = make_engine(db, tmp_path, model)
    await synthesise(engine, "inv-2")
    row = (await db.read("SELECT state, pause_cause FROM investigations WHERE id = 'inv-2'"))[0]
    assert (row["state"], row["pause_cause"]) == ("Paused", "spending_limit")
    assert model.calls == []
    assert await db.read("SELECT 1 FROM reports WHERE investigation_id = 'inv-2'") == []

    for type, payload in (("raise_limit", {"spending_limit_usd": 50}), ("resume", {})):
        await engine.submit(
            Command(id=uuid.uuid4(), type=type, investigation_id="inv-2", payload=payload)
        )
    await asyncio.gather(*engine._background)
    row = (await db.read("SELECT state FROM investigations WHERE id = 'inv-2'"))[0]
    assert row["state"] == "Completed"
    assert len(await db.read("SELECT 1 FROM reports WHERE investigation_id = 'inv-2'")) == 1


async def test_gather_evidence_leaves_out_withdrawn_claims(db, tmp_path):
    await seeded(db, tmp_path, client(), claims=("c-1", "c-2"))
    await append_and_project(db, INV, [ev("claim.withdrawn", {
        "claim_ids": ["c-2"], "cause": "rerun"}, node_id="n-2", actor="user")])  # fmt: skip
    assert [c.id for c in (await gather_evidence(db, INV)).claims] == ["c-1"]
