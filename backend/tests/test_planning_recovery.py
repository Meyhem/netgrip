"""Plan review survives a kill and restart (Phase 3, Task 6)."""

import asyncio
import copy
import json
import uuid

from netgrip.adapters.fakes import SCENARIOS, FakeModelClient
from netgrip.api.investigations import snapshot
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command
from netgrip.config import Config
from netgrip.engine.engine import Engine
from netgrip.store import eventlog
from netgrip.store.db import open_db

GREAT_WALL = json.loads((SCENARIOS / "great_wall.json").read_text(encoding="utf-8"))


class Hanging(FakeModelClient):
    """Never answers the given purposes: the process is 'killed' while waiting."""

    def __init__(self, script: dict, hang: set[str]) -> None:
        super().__init__(script)
        self.hang = hang
        self.entered = asyncio.Event()

    async def complete(self, req):
        if req.purpose in self.hang:
            self.entered.set()
            await asyncio.Event().wait()
        return await super().complete(req)


def script():
    return {"plan.initial": GREAT_WALL["plan.initial"], "plan.replan": GREAT_WALL["plan.replan"]}


def cmd(inv, type, **payload):
    return Command(id=uuid.uuid4(), type=type, investigation_id=inv, payload=payload)


async def open_engine(tmp_path, client, start=True):
    db = await open_db(tmp_path / "n.sqlite")
    eng = Engine(db, Config(data_dir=tmp_path, fake=True), EventBus(), client)
    if start:
        await eng.start()
    return eng


async def kill(eng):
    await eng.stop()
    await eng.db.close()


async def types(eng, inv):
    return [e.type for e in await eventlog.read(eng.db, inv)]


async def planned(eng):
    inv = str(uuid.uuid4())
    await eng.create_investigation(uuid.UUID(inv), "Is the Great Wall visible from space?", {})
    await eng.submit(cmd(inv, "draft_plan"))
    await eng.planning.idle(inv)
    return inv


async def test_restart_in_planning_restores_plan_as_shown(tmp_path):
    eng = await open_engine(tmp_path, FakeModelClient(script()))
    inv = await planned(eng)
    before = await snapshot(inv, eng.db)
    events_before = await types(eng, inv)
    await kill(eng)

    eng = await open_engine(tmp_path, FakeModelClient(script()))
    try:
        await eng.planning.idle(inv)
        assert await snapshot(inv, eng.db) == before
        assert await types(eng, inv) == events_before
        assert before["plan_version"] == 1
    finally:
        await kill(eng)


async def test_queued_instruction_is_applied_once_after_restart(tmp_path):
    client = Hanging(script(), {"plan.replan"})
    eng = await open_engine(tmp_path, client)
    inv = await planned(eng)
    shown = await snapshot(inv, eng.db)
    await eng.submit(cmd(inv, "instruct_plan", text="Drop the marketing angle."))
    await client.entered.wait()
    assert (await types(eng, inv)).count("instruction.applied") == 0
    await kill(eng)

    eng = await open_engine(tmp_path, FakeModelClient(script()))
    try:
        await eng.planning.idle(inv)
        assert (await types(eng, inv)).count("instruction.applied") == 1
        snap = await snapshot(inv, eng.db)
        assert snap["plan_version"] == shown["plan_version"] + 1
        assert [i["state"] for i in snap["instructions"]] == ["applied"]
    finally:
        await kill(eng)

    # A second restart finds nothing queued and applies nothing again.
    eng = await open_engine(tmp_path, FakeModelClient(script()))
    try:
        await eng.planning.idle(inv)
        assert (await types(eng, inv)).count("instruction.applied") == 1
        assert (await snapshot(inv, eng.db))["plan_version"] == snap["plan_version"]
    finally:
        await kill(eng)


async def test_draft_killed_before_plan_arrives_is_redrafted(tmp_path):
    client = Hanging(script(), {"plan.initial"})
    eng = await open_engine(tmp_path, client)
    inv = str(uuid.uuid4())
    await eng.create_investigation(uuid.UUID(inv), "Is the Great Wall visible from space?", {})
    await eng.submit(cmd(inv, "draft_plan"))
    await client.entered.wait()
    assert (await snapshot(inv, eng.db))["plan_version"] == 0
    await kill(eng)

    eng = await open_engine(tmp_path, FakeModelClient(script()))
    try:
        await eng.planning.idle(inv)
        snap = await snapshot(inv, eng.db)
        assert snap["plan_version"] == 1
        assert snap["investigation"]["state"] == "Planning"
        assert snap["plan_failed"] is None
        assert (await types(eng, inv)).count("plan.version_created") == 1
    finally:
        await kill(eng)


async def test_restart_during_a_redraft_drafts_again(tmp_path):
    # R16: plan.draft_requested clears the earlier failure, so recovery resumes the re-draft.
    bad = copy.deepcopy(GREAT_WALL["plan.initial"][0]["parsed"])
    next(n for n in bad["nodes"] if n["ref"] == "D1")["depends_on_refs"] = ["V1"]  # a cycle
    eng = await open_engine(tmp_path, FakeModelClient({"plan.initial": [{"parsed": bad}] * 3}))
    inv = await planned(eng)
    assert (await snapshot(inv, eng.db))["plan_failed"]
    await kill(eng)

    client = Hanging(script(), {"plan.initial"})
    eng = await open_engine(tmp_path, client)
    await eng.planning.idle(inv)
    assert not client.calls  # a failed draft is not retried by itself
    await eng.submit(cmd(inv, "draft_plan"))
    await client.entered.wait()
    snap = await snapshot(inv, eng.db)
    assert snap["plan_failed"] is None and snap["plan_version"] == 0
    await kill(eng)

    eng = await open_engine(tmp_path, FakeModelClient(script()))
    try:
        await eng.planning.idle(inv)
        snap = await snapshot(inv, eng.db)
        assert snap["plan_version"] == 1 and snap["plan_failed"] is None
        all_types = await types(eng, inv)
        assert all_types.count("plan.draft_requested") == 2
        assert all_types.count("plan.version_created") == 1
    finally:
        await kill(eng)
