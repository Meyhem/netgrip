import pytest

from netgrip.boundary.events import EventDraft
from netgrip.engine.ids import next_display_id
from netgrip.store.db import open_db
from netgrip.store.projections import STATE_TABLES, append_and_project
from netgrip.store.rebuild import rebuild

INV = "inv-1"


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def ev(type, data, node_id=None, actor="orchestrator"):
    return EventDraft(type=type, actor=actor, node_id=node_id, data=data)


def proposed(disp, parent=None, deps=(), kind="Divergent", depth=0):
    return {
        "display_id": disp, "parent_id": parent, "kind": kind, "question": f"Q {disp}",
        "justification": "j", "out_of_scope": ["x"], "done_when": "d",
        "depends_on": list(deps), "depth": depth, "proposed_by": "orchestrator",
    }  # fmt: skip


async def seed(db):
    await append_and_project(
        db,
        INV,
        [
            ev("investigation.created", {"prompt": "p", "settings": {}}, actor="user"),
            ev("investigation.root_goal_set", {"root_goal": "goal"}),
            ev("node.proposed", proposed("R", kind="Root"), node_id="n-r"),
            ev("node.proposed", proposed("D1", "n-r", depth=1), node_id="n-1"),
            ev("node.proposed", proposed("D2", "n-r", ["n-1"], depth=1), node_id="n-2"),
            ev("premise.extracted", {"premise_id": "p1", "text": "t", "node_id": "n-1"}),
            ev("plan.version_created", {"version": 1, "instruction_id": None,
                                        "diff": {"proposed": ["n-r", "n-1", "n-2"]}}),
        ],
    )  # fmt: skip


def snap_api(db):
    from netgrip.api.investigations import snapshot

    return snapshot(INV, db)


def test_display_ids():
    assert next_display_id("Root", None, set()) == "R"
    assert next_display_id("Premise check", "R", set()) == "P1"
    assert next_display_id("Premise check", "R", {"P1"}) == "P2"
    assert next_display_id("Divergent", "R", set()) == "D1"
    assert next_display_id("Divergent", "R", {"D1"}) == "D2"
    assert next_display_id("Verification", "R", set()) == "V1"
    assert next_display_id("Synthesis", None, set()) == "S"
    assert next_display_id("Deep-dive", "D2", {"D1", "D2"}) == "D2a"
    assert next_display_id("Deep-dive", "D2", {"D2a"}) == "D2b"
    assert next_display_id("Deep-dive", "D2b", {"D2a", "D2b"}) == "D2b1"
    assert next_display_id("Deep-dive", "D2b1", set()) == "D2b1a"


async def test_proposed_node_in_snapshot_with_deps(db):
    await seed(db)
    s = await snap_api(db)
    assert s["investigation"]["root_goal"] == "goal"
    assert s["plan_version"] == 1
    assert s["plan_failed"] is None
    by = {n["display_id"]: n for n in s["nodes"]}
    assert list(by) == ["R", "D1", "D2"]
    assert by["D2"]["depends_on"] == ["n-1"]
    assert by["D1"]["depends_on"] == []
    assert by["D2"]["status"] == "Proposed" and by["D2"]["inclusion"] == "Included"
    assert by["D2"]["plan_version_added"] == 1
    assert by["D2"]["out_of_scope"] == ["x"]
    assert [p["id"] for p in s["premises"]] == ["p1"]


async def test_inclusion_change_applies_to_listed_nodes(db):
    await seed(db)
    await append_and_project(
        db, INV,
        [ev("node.inclusion_changed",
            {"node_ids": ["n-1", "n-2"], "inclusion": "Ignored", "by": "user",
             "instruction_id": None}),
         ev("node.approved", {"budget": {"max_steps": 3}}, node_id="n-1")],
    )  # fmt: skip
    by = {n["display_id"]: n for n in (await snap_api(db))["nodes"]}
    assert (by["D1"]["inclusion"], by["D2"]["inclusion"], by["R"]["inclusion"]) == (
        "Ignored", "Ignored", "Included")  # fmt: skip
    assert by["D1"]["status"] == "Pending" and by["D1"]["budget"] == {"max_steps": 3}


async def test_instructions_spend_and_failure(db):
    await seed(db)
    spend = {"tier": "fast", "model": "m", "amount_usd": "0.25", "approximate": False,
             "tokens_in": 1, "tokens_out": 1}  # fmt: skip
    await append_and_project(
        db, INV,
        [ev("instruction.queued", {"instruction_id": "i1", "text": "go", "waiting_for": None},
            actor="user"),
         ev("instruction.applied", {"instruction_id": "i1", "at_step": None,
                                    "diff": {"kept": ["n-1"]}}),
         ev("spend.recorded", spend, node_id="n-1"),
         ev("plan.failed", {"reason": "bad"})],
    )  # fmt: skip
    s = await snap_api(db)
    [i] = s["instructions"]
    assert (i["state"], i["node_id"], i["diff"]["kept"]) == ("applied", "n-r", ["n-1"])
    by = {n["display_id"]: n for n in s["nodes"]}
    assert by["R"]["instruction_count"] == 1 and by["D1"]["spent_usd"] == 0.25
    assert s["plan_failed"] == "bad"
    await append_and_project(db, INV, [ev("plan.reverted", {"to_version": 1,
                                                            "instruction_id": "i1"})])  # fmt: skip
    assert (await snap_api(db))["instructions"][0]["state"] == "undone"


async def test_root_goal_set_twice_raises(db):
    await seed(db)
    with pytest.raises(ValueError):
        await append_and_project(db, INV, [ev("investigation.root_goal_set", {"root_goal": "x"})])


async def test_rebuild_reproduces_graph(db):
    await seed(db)
    await append_and_project(
        db, INV,
        [ev("instruction.queued", {"instruction_id": "i1", "text": "go", "waiting_for": None},
            actor="user"),
         ev("instruction.applied", {"instruction_id": "i1", "at_step": None, "diff": {}}),
         ev("node.approved", {"budget": {"a": 1}}, node_id="n-2"),
         ev("plan.failed", {"reason": "bad"})],
    )  # fmt: skip

    async def dump():
        return {t: [tuple(r) for r in await db.read(f"SELECT * FROM {t} ORDER BY 1, 2")]
                for t in STATE_TABLES}  # fmt: skip

    before = await dump()
    snap = await snap_api(db)
    await rebuild(db)
    assert await dump() == before
    assert await snap_api(db) == snap
