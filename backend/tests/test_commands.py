import asyncio
import uuid

import pytest

from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command, CommandRejected
from netgrip.boundary.events import EventDraft
from netgrip.config import Config
from netgrip.engine.engine import Engine, handles
from netgrip.store import eventlog
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project


@handles("test.touch")
async def _touch(engine, tx, cmd):
    return [
        EventDraft(
            type="investigation.state_changed",
            actor="user",
            command_id=str(cmd.id),
            data={"from": "Draft", "to": "Draft", "origin": "user"},
        )
    ]


@pytest.fixture
async def engine(tmp_path):
    db = await open_db(tmp_path / "n.sqlite")
    eng = Engine(db, Config(data_dir=tmp_path), EventBus())
    await eng.start()
    yield eng
    await eng.stop()
    await db.close()


async def new_investigation(engine, prompt="Was the wall visible from orbit?"):
    inv = uuid.uuid4()
    ack = await engine.create_investigation(inv, prompt, {})
    assert ack.recorded and not ack.duplicate
    return str(inv)


def touch(inv, cid=None):
    return Command(id=cid or uuid.uuid4(), type="test.touch", investigation_id=inv, payload={})


async def test_create_emits_created_and_is_draft(engine):
    inv = await new_investigation(engine)
    events = await eventlog.read(engine.db, inv)
    assert [e.type for e in events] == ["investigation.created"]
    [row] = await engine.db.read("SELECT state FROM investigations WHERE id = ?", [inv])
    assert row["state"] == "Draft"


async def test_create_twice_is_noop(engine):
    inv = uuid.uuid4()
    await engine.create_investigation(inv, "p", {})
    ack = await engine.create_investigation(inv, "p", {})
    assert ack.duplicate
    assert len(await eventlog.read(engine.db, str(inv))) == 1


async def test_duplicate_id_is_noop(engine):
    inv = await new_investigation(engine)
    cid = uuid.uuid4()
    first = await engine.submit(touch(inv, cid))
    second = await engine.submit(touch(inv, cid))
    assert (first.duplicate, second.duplicate) == (False, True)
    assert len(await eventlog.read(engine.db, inv)) == 2


async def test_concurrent_duplicates_apply_once(engine):
    inv = await new_investigation(engine)
    cid = uuid.uuid4()
    acks = await asyncio.gather(engine.submit(touch(inv, cid)), engine.submit(touch(inv, cid)))
    assert sorted(a.duplicate for a in acks) == [False, True]
    assert len(await eventlog.read(engine.db, inv)) == 2


async def test_unknown_command_rejected(engine):
    inv = await new_investigation(engine)
    cmd = Command(id=uuid.uuid4(), type="no_such_thing", investigation_id=inv, payload={})
    with pytest.raises(CommandRejected) as exc:
        await engine.submit(cmd)
    assert exc.value.code == "unknown_command"
    assert await engine.db.read("SELECT * FROM commands WHERE id = ?", [str(cmd.id)]) == []


async def test_command_for_missing_investigation_rejected(engine):
    with pytest.raises(CommandRejected) as exc:
        await engine.submit(touch(str(uuid.uuid4())))
    assert exc.value.code == "not_found"


async def test_prompt_kept_verbatim(engine):
    chunk = 'Line "one"\n\tit\'s 🧱 Großе Mauer — 長城\r\n'
    prompt = (chunk * (20_000 // len(chunk) + 1))[:20_000]
    assert len(prompt) == 20_000
    inv = await new_investigation(engine, prompt)
    [event] = await eventlog.read(engine.db, inv)
    assert event.data["prompt"] == prompt
    [row] = await engine.db.read("SELECT prompt FROM investigations WHERE id = ?", [inv])
    assert row["prompt"] == prompt


async def test_subscribe_no_gap_no_duplicate(engine):
    inv = await new_investigation(engine)
    received = []

    async def consume():
        async for item in engine.subscribe(inv, 0):
            received.append(item.seq)
            if item.seq == 200:
                return

    async def produce():
        for _ in range(199):
            await append_and_project(
                engine.db,
                inv,
                [
                    EventDraft(
                        type="investigation.state_changed",
                        actor="system",
                        data={"from": "Draft", "to": "Draft", "origin": "system"},
                    )
                ],
                engine.bus,
            )
            await asyncio.sleep(0)

    await asyncio.wait_for(asyncio.gather(consume(), produce()), timeout=10)
    assert received == list(range(1, 201))


async def test_subscribe_beyond_end_continues_from_end(engine):
    inv = await new_investigation(engine)

    async def first():
        async for item in engine.subscribe(inv, 99):
            return item.seq

    task = asyncio.create_task(first())
    await asyncio.sleep(0.05)
    await engine.submit(touch(inv))
    assert await asyncio.wait_for(task, timeout=2) == 2


async def test_delete_removes_events_and_state(engine):
    inv = await new_investigation(engine)
    other = await new_investigation(engine)
    await engine.submit(touch(inv))
    await engine.delete_investigation(inv)
    assert await eventlog.read(engine.db, inv) == []
    assert await engine.db.read("SELECT * FROM investigations WHERE id = ?", [inv]) == []
    assert await engine.db.read("SELECT * FROM commands WHERE investigation_id = ?", [inv]) == []
    assert len(await eventlog.read(engine.db, other)) == 1
    with pytest.raises(CommandRejected):
        await engine.delete_investigation(inv)
