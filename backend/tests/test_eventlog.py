import json

import pytest
from pydantic import BaseModel, ValidationError

from netgrip.boundary.events import (
    EventDraft,
    UnknownEventType,
    register_event,
    register_upcaster,
)
from netgrip.store import eventlog
from netgrip.store.db import open_db


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def created(prompt="p"):
    return EventDraft(
        type="investigation.created", actor="user", data={"prompt": prompt, "settings": {}}
    )


def changed(to="Planning"):
    return EventDraft(
        type="investigation.state_changed",
        actor="user",
        data={"from": "Draft", "to": to, "origin": "user", "cause": None, "detail": None},
    )


async def test_seq_contiguous_from_one(db):
    async with db.tx() as tx:
        first = await eventlog.append(tx, "a", [created(), changed()])
    async with db.tx() as tx:
        second = await eventlog.append(tx, "a", [changed("Running")])
    assert [e.seq for e in first + second] == [1, 2, 3]
    events = await eventlog.read(db, "a")
    assert [e.seq for e in events] == [1, 2, 3]
    assert events[1].data["from"] == "Draft"
    assert [e.seq for e in await eventlog.read(db, "a", after=1, limit=1)] == [2]


async def test_seq_independent_per_investigation(db):
    async with db.tx() as tx:
        await eventlog.append(tx, "a", [created(), changed()])
        b = await eventlog.append(tx, "b", [created()])
    assert b[0].seq == 1


async def test_unknown_type_rejected(db):
    with pytest.raises(UnknownEventType):
        async with db.tx() as tx:
            await eventlog.append(tx, "a", [EventDraft(type="nope.nope", actor="user")])
    assert await eventlog.read(db, "a") == []


async def test_data_validated_against_model(db):
    bad = EventDraft(type="investigation.created", actor="user", data={"prompt": 3})
    with pytest.raises(ValidationError):
        async with db.tx() as tx:
            await eventlog.append(tx, "a", [bad])
    assert await eventlog.read(db, "a") == []


async def test_old_version_is_upcast_on_read(db):
    class Renamed(BaseModel):
        name: str

    register_event("test.renamed", 1, Renamed)
    register_upcaster("test.renamed", 0, lambda d: {"name": d["title"]})
    async with db.tx() as tx:
        await tx.execute(
            "INSERT INTO events(investigation_id, seq, type, v, at, actor, node_id, command_id,"
            " data) VALUES ('a', 1, 'test.renamed', 0, '2026-01-01T00:00:00.000Z', 'system',"
            " NULL, NULL, ?)",
            [json.dumps({"title": "old"})],
        )
    [event] = await eventlog.read(db, "a")
    assert event.v == 1
    assert event.data == {"name": "old"}
