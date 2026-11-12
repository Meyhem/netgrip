import pytest
from pydantic import BaseModel

from netgrip.boundary.events import EventDraft, register_event
from netgrip.store import eventlog
from netgrip.store.db import open_db
from netgrip.store.projections import STATE_TABLES, append_and_project, projector
from netgrip.store.rebuild import rebuild, verify


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def created(prompt="Was the wall visible?"):
    return EventDraft(
        type="investigation.created",
        actor="user",
        data={"prompt": prompt, "settings": {"spending_limit_usd": 5.0}},
    )


def changed(frm, to, origin="user", cause=None, detail=None):
    return EventDraft(
        type="investigation.state_changed",
        actor="user",
        data={"from": frm, "to": to, "origin": origin, "cause": cause, "detail": detail},
    )


async def dump(db):
    out = {}
    for table in STATE_TABLES:
        rows = await db.read(f"SELECT * FROM {table} ORDER BY 1")
        out[table] = [tuple(r) for r in rows]
    return out


async def test_state_matches_event(db):
    await append_and_project(db, "a", [created()])
    [row] = await db.read("SELECT * FROM investigations")
    assert row["id"] == "a"
    assert row["state"] == "Draft"
    assert row["prompt"] == "Was the wall visible?"
    assert row["last_seq"] == 1
    await append_and_project(
        db, "a", [changed("Draft", "Paused", "system", "outage", "Model provider down")]
    )
    [row] = await db.read("SELECT * FROM investigations")
    assert (row["state"], row["pause_cause"], row["last_seq"]) == ("Paused", "outage", 2)


async def test_projector_error_stores_nothing(db):
    class Boom(BaseModel):
        pass

    register_event("test.boom", 1, Boom)

    @projector("test.boom")
    async def _boom(tx, event):
        raise RuntimeError("projector failed")

    with pytest.raises(RuntimeError):
        await append_and_project(db, "a", [created(), EventDraft(type="test.boom", actor="system")])
    assert await eventlog.read(db, "a") == []
    assert await db.read("SELECT * FROM investigations") == []


async def test_rebuild_reproduces_state(db):
    await append_and_project(db, "a", [created(), changed("Draft", "Planning")])
    await append_and_project(db, "b", [created("other")])
    await append_and_project(db, "a", [changed("Planning", "Paused", "system", "x", "y")])
    before = await dump(db)
    assert await rebuild(db) == 4
    assert await dump(db) == before
    assert await rebuild(db, "a") == 3
    assert await dump(db) == before


async def test_verify_detects_mismatch(db):
    await append_and_project(db, "a", [created()])
    await append_and_project(db, "b", [created()])
    assert await verify(db) == []
    async with db.tx() as tx:
        await tx.execute("UPDATE investigations SET last_seq = 7 WHERE id = 'b'")
    assert await verify(db) == ["b"]
    await rebuild(db, "b")
    assert await verify(db) == []
