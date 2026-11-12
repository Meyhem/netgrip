"""Re-plan by instruction, undo the last instruction, approve the plan (Phase 3, Task 5)."""

import asyncio
import copy
import json
import uuid

import pytest

from netgrip.adapters.fakes import SCENARIOS, FakeModelClient
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command, CommandRejected
from netgrip.config import Config
from netgrip.engine.budget import allocate_budget
from netgrip.engine.engine import Engine
from netgrip.engine.planner import PlanDraft, compute_diff
from netgrip.store import eventlog
from netgrip.store.db import open_db
from netgrip.store.settings import DEFAULT_SETTINGS, Effort

GREAT_WALL = json.loads((SCENARIOS / "great_wall.json").read_text(encoding="utf-8"))
MEDIUM = Effort.model_validate(DEFAULT_SETTINGS["effort"]["Medium"])
INITIAL = GREAT_WALL["plan.initial"][0]
REPLANS = GREAT_WALL["plan.replan"]


class GatedClient(FakeModelClient):
    """Holds every `plan.replan` call until `gate` is set; `entered` is set when one arrives."""

    def __init__(self, script: dict) -> None:
        super().__init__(script)
        self.gate = asyncio.Event()
        self.entered = asyncio.Event()

    async def complete(self, req):
        if req.purpose == "plan.replan":
            self.entered.set()
            await self.gate.wait()
        return await super().complete(req)


@pytest.fixture
async def make_engine(tmp_path):
    made = []

    async def make(replans=None, client_cls=FakeModelClient):
        db = await open_db(tmp_path / f"n{len(made)}.sqlite")
        script = {"plan.initial": [INITIAL], "plan.replan": list(replans or REPLANS)}
        eng = Engine(db, Config(data_dir=tmp_path, fake=True), EventBus(), client_cls(script))
        await eng.start()
        made.append(eng)
        return eng

    yield make
    for eng in made:
        await eng.stop()
        await eng.db.close()


def cmd(inv, type, **payload):
    return Command(id=uuid.uuid4(), type=type, investigation_id=inv, payload=payload)


async def planned(engine):
    """An investigation in Planning with plan version 1 (the Great Wall draft)."""
    inv = str(uuid.uuid4())
    await engine.create_investigation(uuid.UUID(inv), "Is the Great Wall visible from space?", {})
    await engine.submit(cmd(inv, "draft_plan"))
    await engine.planning.idle(inv)
    return inv


async def instruct(engine, inv, text="Drop the marketing angle; look at origins and photos."):
    await engine.submit(cmd(inv, "instruct_plan", text=text))
    await engine.planning.idle(inv)


async def events_after(engine, inv, seq):
    return [e for e in await eventlog.read(engine.db, inv) if e.seq > seq]


async def last_seq(engine, inv):
    return (await eventlog.read(engine.db, inv))[-1].seq


async def nodes(engine, inv):
    rows = await engine.db.read(
        "SELECT id, display_id, status, inclusion, budget, instruction_count, parent_id"
        " FROM nodes WHERE investigation_id = ? ORDER BY seq",
        [inv],
    )
    return {r["display_id"]: dict(r) for r in rows}


async def version(engine, inv):
    rows = await engine.db.read(
        "SELECT COALESCE(MAX(version), 0) FROM plan_versions WHERE investigation_id = ?", [inv]
    )
    return rows[0][0]


async def included(engine, inv):
    return {d for d, n in (await nodes(engine, inv)).items() if n["inclusion"] == "Included"}


async def rejected(engine, command):
    with pytest.raises(CommandRejected) as exc:
        await engine.submit(command)
    return exc.value.code


def draft_without(entry, *refs):
    d = copy.deepcopy(entry["parsed"])
    d["nodes"] = [n for n in d["nodes"] if n["ref"] not in refs]
    return {"parsed": d}


# --- the listed tests ------------------------------------------------------------------------


async def test_instruction_adds_and_supersedes_with_diff(make_engine):
    engine = await make_engine()
    inv = await planned(engine)
    before = await nodes(engine, inv)
    seq = await last_seq(engine, inv)
    text = "Drop the marketing angle; look at origins and photos."
    await instruct(engine, inv, text)

    events = await events_after(engine, inv, seq)
    assert [e.type for e in events] == [
        "instruction.queued",
        "spend.recorded",
        "node.proposed",
        "node.proposed",
        "node.inclusion_changed",
        "instruction.applied",
        "plan.version_created",
    ]
    queued = events[0]
    root = before["R"]["id"]
    assert queued.node_id == root
    iid = queued.data["instruction_id"]
    assert queued.data == {"instruction_id": iid, "text": text, "waiting_for": "replan"}

    after = await nodes(engine, inv)
    new = [e for e in events if e.type == "node.proposed"]
    assert [e.data["display_id"] for e in new] == ["D4", "D5"]
    for e in new:  # new children of R wait on the premise check (I2)
        assert e.data["parent_id"] == root and e.data["depth"] == 1
        assert before["P1"]["id"] in e.data["depends_on"]
        assert e.data["proposed_by"] == "planner"

    sup = events[4]
    assert sup.data == {"node_ids": [before["D3"]["id"]], "inclusion": "Superseded",
                        "by": "replan", "instruction_id": iid}  # fmt: skip
    diff = {
        "kept": [before[d]["id"] for d in ("P1", "D1", "D2", "D2a", "V1")],
        "superseded": [before["D3"]["id"]],
        "proposed": [after["D4"]["id"], after["D5"]["id"]],
        "notes": [],
    }
    assert events[5].data == {"instruction_id": iid, "at_step": None, "diff": diff}
    assert events[6].data == {"version": 2, "instruction_id": iid, "diff": diff}

    assert after["D3"]["inclusion"] == "Superseded"
    assert await included(engine, inv) == {"R", "P1", "D1", "D2", "D2a", "V1", "D4", "D5"}
    assert after["R"]["instruction_count"] == 1
    [ins] = await engine.db.read("SELECT state, undone FROM instructions WHERE id = ?", [iid])
    assert ins["state"] == "applied" and ins["undone"] == 0
    assert await version(engine, inv) == 2

    # The model got the current plan, refs = display ids, and the instruction as data.
    [call] = [c for c in engine.model_client.calls if c.purpose == "plan.replan"]
    assert call.tier == "strong" and call.tools is None and call.response_schema is not None
    content = call.messages[-1].content
    assert text in content and '"ref": "D3"' in content and '"ref": "D2a"' in content


async def test_two_instructions_apply_in_order_as_versions_2_and_3(make_engine):
    engine = await make_engine(client_cls=GatedClient)
    inv = await planned(engine)
    seq = await last_seq(engine, inv)
    await engine.submit(cmd(inv, "instruct_plan", text="first instruction"))
    await engine.model_client.entered.wait()  # the first re-plan is running
    await engine.submit(cmd(inv, "instruct_plan", text="second instruction"))
    engine.model_client.gate.set()
    await engine.planning.idle(inv)

    events = await events_after(engine, inv, seq)
    queued = [e.data["instruction_id"] for e in events if e.type == "instruction.queued"]
    applied = [e.data["instruction_id"] for e in events if e.type == "instruction.applied"]
    versions = [(e.data["version"], e.data["instruction_id"])
                for e in events if e.type == "plan.version_created"]  # fmt: skip
    assert applied == queued
    assert versions == [(2, queued[0]), (3, queued[1])]
    # The second re-plan saw the first one's result and both instructions.
    second = [c for c in engine.model_client.calls if c.purpose == "plan.replan"][1]
    content = second.messages[-1].content
    assert "first instruction" in content and "second instruction" in content
    assert '"ref": "D4"' in content and '"ref": "D3"' not in content
    # Replan 2 of the scenario drops D2a and keeps D4, D5.
    assert await included(engine, inv) == {"R", "P1", "D1", "D2", "V1", "D4", "D5"}
    assert (await nodes(engine, inv))["R"]["instruction_count"] == 2


async def test_premise_cannot_be_removed_and_note_is_recorded(make_engine):
    engine = await make_engine([draft_without(REPLANS[0], "P1")])
    inv = await planned(engine)
    before = await nodes(engine, inv)
    seq = await last_seq(engine, inv)
    await instruct(engine, inv, "Forget the premise check.")

    events = await events_after(engine, inv, seq)
    [created] = [e for e in events if e.type == "plan.version_created"]
    diff = created.data["diff"]
    assert before["P1"]["id"] in diff["kept"]
    assert before["P1"]["id"] not in diff["superseded"]
    assert diff["notes"] == ["P1 kept: premises are always checked"]
    after = await nodes(engine, inv)
    assert after["P1"]["inclusion"] == "Included"
    for e in (e for e in events if e.type == "node.proposed"):
        assert before["P1"]["id"] in e.data["depends_on"]


async def test_undo_restores_previous_version(make_engine):
    engine = await make_engine()
    inv = await planned(engine)
    v1 = await included(engine, inv)
    await instruct(engine, inv)
    after = await nodes(engine, inv)
    [ins] = await engine.db.read("SELECT id FROM instructions WHERE investigation_id = ?", [inv])
    iid = ins["id"]
    seq = await last_seq(engine, inv)

    await engine.submit(cmd(inv, "undo_plan_instruction"))
    events = await events_after(engine, inv, seq)
    assert [e.type for e in events] == [
        "node.inclusion_changed", "node.inclusion_changed", "plan.reverted",
    ]  # fmt: skip
    restore = {"by": "replan", "instruction_id": iid}
    assert events[0].data == {
        "node_ids": [after["D4"]["id"], after["D5"]["id"]],
        "inclusion": "Superseded",
        **restore,
    }
    assert events[1].data == {"node_ids": [after["D3"]["id"]], "inclusion": "Included", **restore}
    assert events[2].data == {"to_version": 1, "instruction_id": iid}
    assert await included(engine, inv) == v1
    assert await version(engine, inv) == 1
    [row] = await engine.db.read("SELECT state, undone FROM instructions WHERE id = ?", [iid])
    assert row["state"] == "undone" and row["undone"] == 1

    # R7: the next instruction creates version 2 again.
    await instruct(engine, inv, "Try again.")
    assert await version(engine, inv) == 2
    [v2] = await engine.db.read(
        "SELECT instruction_id FROM plan_versions WHERE investigation_id = ? AND version = 2",
        [inv],
    )
    assert v2["instruction_id"] != iid
    # The superseded nodes of the undone instruction stay visible, greyed out (U3).
    assert (await nodes(engine, inv))["D4"]["inclusion"] == "Superseded"


async def test_undo_refused_at_version_1(make_engine):
    engine = await make_engine()
    inv = await planned(engine)
    assert await rejected(engine, cmd(inv, "undo_plan_instruction")) == "nothing_to_undo"
    # Undo twice: the second has nothing left.
    await instruct(engine, inv)
    await engine.submit(cmd(inv, "undo_plan_instruction"))
    assert await rejected(engine, cmd(inv, "undo_plan_instruction")) == "nothing_to_undo"
    assert await version(engine, inv) == 1


async def test_approve_makes_nodes_pending_and_state_running(make_engine):
    engine = await make_engine()
    inv = await planned(engine)
    await instruct(engine, inv)
    seq = await last_seq(engine, inv)
    await engine.submit(cmd(inv, "approve_plan"))

    events = await events_after(engine, inv, seq)
    approved = [e for e in events if e.type == "node.approved"]
    by_id = {n["id"]: d for d, n in (await nodes(engine, inv)).items()}
    assert {by_id[e.node_id] for e in approved} == {
        "R", "P1", "D1", "D2", "D2a", "V1", "D4", "D5",
    }  # fmt: skip
    assert events[-1].type == "investigation.state_changed"
    assert events[-1].data["from"] == "Planning" and events[-1].data["to"] == "Running"
    assert events[-1].data["origin"] == "user"

    after = await nodes(engine, inv)
    for d in ("R", "P1", "D1", "D4"):
        assert after[d]["status"] == "Pending"
        assert json.loads(after[d]["budget"]) == {"sources": 8, "child_nodes": 20}
    assert json.loads(after["D2a"]["budget"]) == {"sources": 6, "child_nodes": 10}
    assert after["D3"]["status"] == "Proposed" and after["D3"]["inclusion"] == "Superseded"
    assert after["D3"]["budget"] is None
    [row] = await engine.db.read("SELECT state FROM investigations WHERE id = ?", [inv])
    assert row["state"] == "Running"

    # Nothing of the plan can be changed now.
    for c in ("instruct_plan", "undo_plan_instruction", "approve_plan"):
        assert await rejected(engine, cmd(inv, c, text="x")) == "wrong_state"


async def test_approve_refused_while_replanning(make_engine):
    engine = await make_engine(client_cls=GatedClient)
    inv = await planned(engine)
    await engine.submit(cmd(inv, "instruct_plan", text="look at origins"))
    await engine.model_client.entered.wait()
    assert await rejected(engine, cmd(inv, "approve_plan")) == "replanning"
    assert await rejected(engine, cmd(inv, "undo_plan_instruction")) == "replanning"
    engine.model_client.gate.set()
    await engine.planning.idle(inv)
    await engine.submit(cmd(inv, "approve_plan"))
    [row] = await engine.db.read("SELECT state FROM investigations WHERE id = ?", [inv])
    assert row["state"] == "Running"


def test_budget_shrinks_with_depth():
    assert allocate_budget(MEDIUM, 1).sources == 8
    assert allocate_budget(MEDIUM, 3).sources in (4, 5)
    sources = [allocate_budget(MEDIUM, d).sources for d in range(1, 12)]
    assert sources == sorted(sources, reverse=True)
    assert min(sources) == 2
    low = Effort.model_validate(DEFAULT_SETTINGS["effort"]["Low"])
    assert allocate_budget(low, 1).sources == 4 and allocate_budget(low, 3).sources == 2
    assert allocate_budget(low, 2).child_nodes == 0  # Low allows depth 2 at most
    # Children: halve per level; none at the deepest allowed level (it cannot have children).
    assert [allocate_budget(MEDIUM, d).child_nodes for d in (1, 2, 3, 4)] == [20, 10, 5, 0]


# --- further behaviour -----------------------------------------------------------------------


async def test_wrong_state_before_a_plan_exists(make_engine):
    engine = await make_engine()
    inv = str(uuid.uuid4())
    await engine.create_investigation(uuid.UUID(inv), "prompt", {})
    for c in ("instruct_plan", "undo_plan_instruction", "approve_plan"):
        assert await rejected(engine, cmd(inv, c, text="x")) == "wrong_state"


async def test_empty_instruction_rejected(make_engine):
    engine = await make_engine()
    inv = await planned(engine)
    assert await rejected(engine, cmd(inv, "instruct_plan", text="  ")) == "empty_instruction"


async def test_failed_replan_keeps_the_version_and_records_spend(make_engine):
    bad = {"parsed": {"root_goal": "g"}, "usage": {"cost_usd": "0.02"}}
    engine = await make_engine([bad] * 3)
    inv = await planned(engine)
    v1 = await included(engine, inv)
    seq = await last_seq(engine, inv)
    await instruct(engine, inv)

    events = await events_after(engine, inv, seq)
    assert [e.type for e in events] == [
        "instruction.queued", *["spend.recorded"] * 3, "plan.failed", "instruction.applied",
    ]  # fmt: skip
    applied = events[-1].data
    assert applied["diff"]["kept"] == [] and applied["diff"]["proposed"] == []
    [note] = applied["diff"]["notes"]
    assert note.startswith("Re-plan failed: ")
    assert await version(engine, inv) == 1
    assert await included(engine, inv) == v1
    # Nothing to undo: a failed re-plan made no version.
    assert await rejected(engine, cmd(inv, "undo_plan_instruction")) == "nothing_to_undo"


async def test_replan_model_unavailable(make_engine):
    engine = await make_engine([{"raise": "unavailable"}])
    inv = await planned(engine)
    await instruct(engine, inv)
    events = await eventlog.read(engine.db, inv)
    assert [e.type for e in events][-2:] == ["plan.failed", "instruction.applied"]
    assert "unavailable" in events[-1].data["diff"]["notes"][0]
    assert await version(engine, inv) == 1


def test_compute_diff_matches_by_ref():
    old = [
        {"id": "id-p1", "display_id": "P1", "kind": "Premise check"},
        {"id": "id-d1", "display_id": "D1", "kind": "Divergent"},
        {"id": "id-d3", "display_id": "D3", "kind": "Divergent"},
    ]
    d = PlanDraft.model_validate(draft_without(REPLANS[0], "P1")["parsed"])
    diff = compute_diff(old, d)
    assert diff.kept == ["id-p1", "id-d1"]
    assert diff.superseded == ["id-d3"]
    assert diff.proposed == ["D2", "D2a", "V1", "D4", "D5"]
    assert diff.notes == ["P1 kept: premises are always checked"]


# --- fix round 1: a re-plan must not orphan kept nodes ---------------------------------------


async def test_dropping_a_parent_but_keeping_its_child_is_retried(make_engine):
    orphan = draft_without(REPLANS[0], "D2")
    for n in orphan["parsed"]["nodes"]:
        if n["ref"] == "D2a":
            n["parent_ref"] = None
        if n["ref"] == "V1":
            n["depends_on_refs"] = ["D1"]
    engine = await make_engine([orphan, REPLANS[0]])
    inv = await planned(engine)
    await instruct(engine, inv)
    calls = [c for c in engine.model_client.calls if c.purpose == "plan.replan"]
    assert len(calls) == 2
    retry = calls[1].messages[-1].content
    assert "D2a" in retry and "D2" in retry
    assert await version(engine, inv) == 2
    assert await included(engine, inv) == {"R", "P1", "D1", "D2", "D2a", "V1", "D4", "D5"}


async def test_dropping_a_dependency_of_a_kept_node_is_retried(make_engine):
    dropped = draft_without(REPLANS[0], "D1")
    for n in dropped["parsed"]["nodes"]:
        if n["ref"] in ("V1", "D2a"):
            n["depends_on_refs"] = [d for d in n["depends_on_refs"] if d != "D1"]
    engine = await make_engine([dropped, REPLANS[0]])
    inv = await planned(engine)
    await instruct(engine, inv)
    calls = [c for c in engine.model_client.calls if c.purpose == "plan.replan"]
    assert len(calls) == 2
    retry = calls[1].messages[-1].content
    assert "V1" in retry and "D1" in retry
    assert await version(engine, inv) == 2
    assert "D1" in await included(engine, inv)


async def test_orphaning_drafts_fail_after_the_retries(make_engine):
    orphan = draft_without(REPLANS[0], "D2")
    for n in orphan["parsed"]["nodes"]:
        if n["ref"] == "D2a":
            n["parent_ref"] = None
        if n["ref"] == "V1":
            n["depends_on_refs"] = ["D1"]
    engine = await make_engine([orphan] * 3)
    inv = await planned(engine)
    v1 = await included(engine, inv)
    await instruct(engine, inv)
    events = await eventlog.read(engine.db, inv)
    assert [e.type for e in events][-2:] == ["plan.failed", "instruction.applied"]
    assert await version(engine, inv) == 1 and await included(engine, inv) == v1


# --- final phase review fixes ----------------------------------------------------------------


def replan_draft(*edits):
    """The plan of version 1 as a re-plan draft, changed by `edits` (functions of the dict)."""
    d = copy.deepcopy(INITIAL["parsed"])
    for edit in edits:
        edit(d)
    return {"parsed": d}


def find(d, ref):
    return next(n for n in d["nodes"] if n["ref"] == ref)


async def test_replan_adding_a_premise_check_is_rejected_and_retried(make_engine):
    # R13: premises come from the question; an instruction cannot add one.
    def add_premise(d):
        d["premises"].append({"ref": "P2", "text": "Astronauts said they saw it."})
        d["nodes"].append(
            {"ref": "P2", "parent_ref": None, "kind": "Premise check",
             "question": "Did astronauts say they saw it?", "justification": "An assumption.",
             "out_of_scope": "", "done_when": "Answered.", "depends_on_refs": []}
        )  # fmt: skip

    engine = await make_engine([replan_draft(add_premise), REPLANS[0]])
    inv = await planned(engine)
    await instruct(engine, inv, "Assume astronauts saw it.")
    calls = [c for c in engine.model_client.calls if c.purpose == "plan.replan"]
    assert len(calls) == 2
    retry = calls[1].messages[-1].content
    assert "P2" in retry and "cannot be added by an instruction" in retry
    assert "cannot be added by an instruction" in calls[0].system
    assert await version(engine, inv) == 2
    premises = await engine.db.read("SELECT text FROM premises WHERE investigation_id = ?", [inv])
    assert len(premises) == 1
    assert "P2" not in await included(engine, inv)


async def test_editing_a_kept_node_in_place_is_retried_and_a_new_ref_applies(make_engine):
    # R14: a kept node cannot be edited; the model must drop it and add a new node instead.
    def edit_d1(d):
        find(d, "D1")["question"] = "When and why was the Wall built?"

    def replace_d1(d):
        d1 = find(d, "D1")
        d["nodes"] = [n for n in d["nodes"] if n["ref"] not in ("D1", "D2a", "V1")]
        d["nodes"] += [
            {**d1, "ref": "N1", "question": "When and why was the Wall built?"},
            # D2a and V1 depend on D1, so they are replaced too; N2 sits under the kept D2.
            {**find(INITIAL["parsed"], "D2a"), "ref": "N2", "depends_on_refs": []},
            {**find(INITIAL["parsed"], "V1"), "ref": "N3", "depends_on_refs": ["N1", "D2"]},
        ]

    engine = await make_engine([replan_draft(edit_d1), replan_draft(replace_d1)])
    inv = await planned(engine)
    before = await nodes(engine, inv)
    await instruct(engine, inv, "Focus D1 on when and why the Wall was built.")
    calls = [c for c in engine.model_client.calls if c.purpose == "plan.replan"]
    assert len(calls) == 2
    retry = calls[1].messages[-1].content
    assert "D1" in retry and "question" in retry and "new ref" in retry
    assert "drop" in calls[0].system or "leave out its ref" in calls[0].system
    assert await version(engine, inv) == 2
    after = await nodes(engine, inv)
    assert after["D1"]["inclusion"] == "Superseded"
    assert after["D1"]["id"] == before["D1"]["id"]
    new = await engine.db.read(
        "SELECT id, display_id, question, depth FROM nodes WHERE investigation_id = ?"
        " AND question = 'When and why was the Wall built?'",
        [inv],
    )
    assert len(new) == 1 and new[0]["display_id"] not in before
    # R13: a new node at depth 2 with no dependencies of its own waits on P1.
    deep = next(
        n for d, n in after.items() if d not in before and n["parent_id"] == before["D2"]["id"]
    )
    deps = await engine.db.read(
        "SELECT depends_on_id FROM node_deps WHERE node_id = ?", [deep["id"]]
    )
    assert [r[0] for r in deps] == [before["P1"]["id"]]


async def test_replan_request_refused_is_not_retried(make_engine):
    engine = await make_engine([{"raise": "request"}])
    inv = await planned(engine)
    await instruct(engine, inv)
    assert len([c for c in engine.model_client.calls if c.purpose == "plan.replan"]) == 1
    events = await eventlog.read(engine.db, inv)
    assert [e.type for e in events][-2:] == ["plan.failed", "instruction.applied"]
    assert events[-2].data["reason"].startswith("The model provider refused the request:")
    assert events[-1].data["diff"]["notes"] == [
        "Re-plan failed: the model provider refused the request."
    ]
    assert await version(engine, inv) == 1


async def test_unexpected_error_outside_the_model_call_fails_the_replan(make_engine, monkeypatch):
    # M3: the instruction is never left queued forever.
    from netgrip.engine import planner

    def broken(*a, **kw):
        raise RuntimeError("boom")

    engine = await make_engine()
    inv = await planned(engine)
    monkeypatch.setattr(planner, "replan_events", broken)
    await instruct(engine, inv)
    events = await eventlog.read(engine.db, inv)
    assert [e.type for e in events][-2:] == ["plan.failed", "instruction.applied"]
    assert events[-1].data["diff"]["notes"] == ["Re-plan failed: an unexpected error."]
    states = await engine.db.read(
        "SELECT state FROM instructions WHERE investigation_id = ?", [inv]
    )
    assert [r["state"] for r in states] == ["applied"]
    assert await version(engine, inv) == 1
    assert not engine.planning.busy(inv)
