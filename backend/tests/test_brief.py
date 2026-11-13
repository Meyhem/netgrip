import json

import pytest

from netgrip.boundary.events import EventDraft
from netgrip.engine.brief import build_brief, render_brief
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project

INV = "inv-1"
GOAL = "Why did the  Wall fall?\n(verbatim, odd   spacing)"
BUDGET = {"sources": 6, "depth": 2, "nodes": 3}


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def ev(type, data, node_id=None, actor="orchestrator"):
    return EventDraft(type=type, actor=actor, node_id=node_id, data=data)


def proposed(disp, parent=None, deps=(), kind="Divergent", depth=0, question=None):
    return {
        "display_id": disp, "parent_id": parent, "kind": kind,
        "question": question or f"Question {disp}",
        "justification": f"why {disp}", "out_of_scope": f"not {disp}",
        "done_when": f"done {disp}", "depends_on": list(deps), "depth": depth,
        "proposed_by": "orchestrator",
    }  # fmt: skip


@pytest.fixture
async def graph(db):
    """R -> D1 -> D1a ; R -> D2 (depends on D1) ; R -> D3 (sibling of D1/D2)."""
    evs = [
        ev("investigation.created", {"prompt": "p", "settings": {}}, actor="user"),
        ev("investigation.root_goal_set", {"root_goal": GOAL}),
        ev("node.proposed", proposed("R", kind="Root"), node_id="n-r"),
        ev("node.proposed", proposed("D1", "n-r", depth=1), node_id="n-1"),
        ev(
            "node.proposed", proposed("D1a", "n-1", depth=2, question="wall height"), node_id="n-1a"
        ),
        ev("node.proposed", proposed("D2", "n-r", ["n-1"], depth=1), node_id="n-2"),
        ev("node.proposed", proposed("D3", "n-r", depth=1), node_id="n-3"),
    ]
    for n in ("n-r", "n-1", "n-1a", "n-2", "n-3"):
        evs.append(ev("node.approved", {"budget": BUDGET}, node_id=n))
    await append_and_project(db, INV, evs)
    return db


async def test_root_goal_is_verbatim(graph):
    b = await build_brief(graph, "n-1a")
    assert b.root_goal == GOAL
    assert GOAL in render_brief(b)


async def test_path_lists_ancestors_root_first(graph):
    b = await build_brief(graph, "n-1a")
    assert [p.display_id for p in b.path] == ["R", "D1"]
    assert b.path[1].question == "Question D1" and b.path[1].justification == "why D1"
    assert b.task.question == "wall height"
    assert b.task.out_of_scope == "not D1a" and b.task.done_when == "done D1a"
    assert b.task.budget == BUDGET
    root = await build_brief(graph, "n-r")
    assert root.path == []


async def test_dependency_results_included(graph):
    verdict = {"text": "It was long", "confidence": "high"}
    await complete(graph, "n-1", verdict)
    b = await build_brief(graph, "n-2")
    assert [(d.display_id, d.verdict) for d in b.known.dependency_results] == [("D1", verdict)]
    assert "It was long" in render_brief(b)


async def test_dependency_not_completed_is_absent(graph):
    b = await build_brief(graph, "n-2")
    assert b.known.dependency_results == []


async def test_sibling_outputs_absent(graph):
    secret = {"text": "SIBLING-SECRET", "confidence": "low"}
    await complete(graph, "n-3", secret)
    await complete(graph, "n-1", secret)
    b = await build_brief(graph, "n-2")  # D3 is a sibling and not a dependency
    dumped = json.dumps(b.model_dump()) + render_brief(b)
    assert "D3" not in dumped and "Question D3" not in dumped
    assert [d.display_id for d in b.known.dependency_results] == ["D1"]  # D1 is declared
    b1a = await build_brief(graph, "n-1a")
    assert "SIBLING-SECRET" not in json.dumps(b1a.model_dump()) + render_brief(b1a)
    assert "D2" not in json.dumps(b1a.model_dump())


async def complete(db, node_id, verdict):
    data = {"verdict": verdict, "open_questions": [], "off_topic": False}
    await append_and_project(db, INV, [ev("node.completed", data, node_id=node_id, actor="node")])


async def _instruct(db, iid, node_id, text, applied=True):
    evs = [ev("instruction.queued", {"instruction_id": iid, "text": text}, node_id=node_id,
              actor="user")]  # fmt: skip
    if applied:
        evs.append(ev("instruction.applied", {"instruction_id": iid, "at_step": None, "diff": {}}))
    await append_and_project(db, INV, evs)


async def test_inherited_instructions_included_with_origin(graph):
    await _instruct(graph, "i1", "n-r", "Prefer primary sources")
    await _instruct(graph, "i2", "n-1", "Skip blogs")
    await _instruct(graph, "i3", "n-1", "Undone one")
    await append_and_project(
        graph, INV, [ev("plan.reverted", {"instruction_id": "i3", "to_version": 0})]
    )
    await _instruct(graph, "i4", "n-1", "Still queued", applied=False)
    await _instruct(graph, "i5", "n-3", "Only for D3")
    await _instruct(graph, "i6", "n-1a", "Own instruction")
    b = await build_brief(graph, "n-1a")
    assert [(i.text, i.from_display_id) for i in b.known.instructions] == [
        ("Prefer primary sources", "R"),
        ("Skip blogs", "D1"),
        ("Own instruction", "D1a"),
    ]


async def _claim(db, cid, text):
    await append_and_project(
        db, INV,
        [ev("source.recorded", {"source_id": "s" + cid, "url": "https://a.org/" + cid,
                                "title": None, "page_version_id": "pv" + cid,
                                "credibility": "Reputable", "published_at": None,
                                "origin_key": "a.org"}, node_id="n-3"),
         ev("claim.added", {"claim_id": cid, "text": text, "status": "Supported",
                            "supporting": ["s" + cid], "contradicting": []}, node_id="n-3")],
    )  # fmt: skip


async def test_known_claims_limited_to_relevant(graph):
    await _claim(graph, "c1", "The wall height is 5 metres")
    await _claim(graph, "c2", "Cheese is made from milk")
    for i in range(20):
        await _claim(graph, f"w{i}", f"wall segment {i} height noted")
    b = await build_brief(graph, "n-1a")
    texts = [c.text for c in b.known.claims]
    assert "Cheese is made from milk" not in texts
    assert texts[0] == "The wall height is 5 metres"
    assert len(texts) <= 10
    assert b.known.claims[0].status == "Supported" and b.known.claims[0].id == "c1"


async def test_brief_is_json_serialisable(graph):
    await _claim(graph, "c1", "The wall height is 5 metres")
    b = await build_brief(graph, "n-1a")
    assert json.loads(json.dumps(b.model_dump(mode="json")))["root_goal"] == GOAL


async def fail(db, node_id, reason, left=True):
    evs = [ev("node.failed", {"reason": reason, "auto_retry_used": False}, node_id, actor="node")]
    if left:
        evs.append(ev("node.left_failed", {"reason": "auto_retry_used"}, node_id))
    await append_and_project(db, INV, evs)


async def test_dependency_left_failed_is_listed_with_its_reason(graph):
    await fail(graph, "n-1", "every page was unobtainable")
    b = await build_brief(graph, "n-2")
    assert [(d.display_id, d.verdict, d.failed) for d in b.known.dependency_results] == [
        ("D1", None, "every page was unobtainable")
    ]
    assert "D1: failed, no verdict (every page was unobtainable)" in render_brief(b)


async def test_dependency_failed_but_not_yet_decided_is_absent(graph):
    await fail(graph, "n-1", "boom", left=False)  # the retry decision is still owed
    b = await build_brief(graph, "n-2")
    assert b.known.dependency_results == []
