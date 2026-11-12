"""The live stream, against a real server: ASGI test transports buffer whole responses."""

import asyncio
import json
import socket
import uuid

import httpx
import pytest
import uvicorn

from netgrip.app import create_app
from netgrip.boundary.bus import Ephemeral
from netgrip.boundary.events import EventDraft
from netgrip.store.projections import append_and_project


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def server(config):
    app = create_app(config)
    port = free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(srv.serve())
    while not srv.started:
        await asyncio.sleep(0.01)
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=5) as client:
        client.app = app
        yield client
    srv.should_exit = True
    await task


async def touch(app, inv, n=1):
    engine = app.state.engine
    data = {"from": "Draft", "to": "Draft", "origin": "system"}
    for _ in range(n):
        draft = EventDraft(type="investigation.state_changed", actor="system", data=data)
        await append_and_project(engine.db, inv, [draft], engine.bus)


async def create(client):
    inv = str(uuid.uuid4())
    r = await client.post("/api/investigations", json={"id": inv, "prompt": "p", "settings": {}})
    assert r.status_code == 202
    return inv


async def read_messages(client, url, count, headers=None):
    """Read `count` SSE messages (comments skipped) as dicts of field -> value."""
    out, current = [], {}
    async with client.stream("GET", url, headers=headers or {}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        async for line in r.aiter_lines():
            if line == "":
                if current:
                    out.append(current)
                    current = {}
                    if len(out) == count:
                        return out
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            current[field] = value.removeprefix(" ")
    return out


async def test_stream_resumes_after_seq(server):
    inv = await create(server)
    await touch(server.app, inv, 4)
    url = f"/api/investigations/{inv}/stream"
    first = await asyncio.wait_for(read_messages(server, url, 3), 5)
    assert [m["id"] for m in first] == ["1", "2", "3"]
    assert all(m["event"] == "durable" for m in first)
    assert json.loads(first[0]["data"])["type"] == "investigation.created"
    again = await asyncio.wait_for(read_messages(server, url, 1, {"Last-Event-ID": "3"}), 5)
    assert again[0]["id"] == "4"
    by_query = await asyncio.wait_for(read_messages(server, url + "?after=4", 1), 5)
    assert by_query[0]["id"] == "5"


async def test_stream_after_beyond_end_waits(server):
    inv = await create(server)
    url = f"/api/investigations/{inv}/stream?after=500"
    reader = asyncio.create_task(read_messages(server, url, 2))
    await asyncio.sleep(0.2)
    assert not reader.done()
    server.app.state.engine.publish_ephemeral(
        Ephemeral(investigation_id=inv, node_id="n1", kind="model_text", data={"text": "hi"})
    )
    await touch(server.app, inv)
    eph, durable = await asyncio.wait_for(reader, 5)
    assert eph["event"] == "ephemeral" and "id" not in eph
    assert json.loads(eph["data"])["data"] == {"text": "hi"}
    assert durable["event"] == "durable" and durable["id"] == "2"


async def test_stream_unknown_investigation_is_404(server):
    r = await server.get(f"/api/investigations/{uuid.uuid4()}/stream")
    assert r.status_code == 404
