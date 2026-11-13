import logging
import uuid


async def create(client, prompt="Was the Great Wall visible from orbit?", settings=None):
    inv = str(uuid.uuid4())
    r = await client.post(
        "/api/investigations", json={"id": inv, "prompt": prompt, "settings": settings or {}}
    )
    assert r.status_code == 202, r.text
    return inv


async def test_create_then_list_then_snapshot(app_client):
    inv = await create(app_client, settings={"effort": "High"})
    rows = (await app_client.get("/api/investigations")).json()
    [row] = rows
    assert row["id"] == inv
    assert row["state"] == "Draft"
    assert row["effort"] == "High"
    assert (row["nodes_total"], row["nodes_max"]) == (0, 80)
    assert row["spending_limit_usd"] == 5.0
    assert row["summary"] is None
    expected = {
        "id", "prompt", "state", "pause_cause", "pause_detail", "effort", "nodes_total",
        "nodes_max", "running_count", "spent_usd", "spend_approximate", "spending_limit_usd",
        "disk_bytes", "run_seconds", "last_activity_at", "summary",
    }  # fmt: skip
    assert set(row) == expected

    snap = (await app_client.get(f"/api/investigations/{inv}")).json()
    assert snap["seq"] == 1
    assert snap["investigation"]["id"] == inv
    assert snap["investigation"]["settings"]["tiers"]["strong"] == "anthropic/claude-opus-5.5"
    assert snap["investigation"]["root_goal"] is None
    assert snap["nodes"] == [] and snap["instructions"] == [] and snap["premises"] == []
    assert snap["schedule"] == {"order": [], "reasons": {}, "slots": 0}
    assert snap["focus_node_id"] is None and snap["plan_version"] == 0

    events = (await app_client.get(f"/api/investigations/{inv}/events?after=0")).json()
    assert [e["type"] for e in events] == ["investigation.created"]
    assert (await app_client.get(f"/api/investigations/{uuid.uuid4()}")).status_code == 404


async def test_create_duplicate_and_invalid(app_client):
    inv = str(uuid.uuid4())
    body = {"id": inv, "prompt": "p", "settings": {}}
    first = (await app_client.post("/api/investigations", json=body)).json()
    second = (await app_client.post("/api/investigations", json=body)).json()
    assert (first["duplicate"], second["duplicate"]) == (False, True)
    bad = {"id": str(uuid.uuid4()), "prompt": "p", "settings": {"effort": "Huge"}}
    assert (await app_client.post("/api/investigations", json=bad)).status_code == 422
    empty = {"id": str(uuid.uuid4()), "prompt": "  ", "settings": {}}
    r = await app_client.post("/api/investigations", json=empty)
    assert r.status_code == 409 and r.json()["code"] == "empty_prompt"


async def test_command_route_returns_202_and_duplicate_flag(app_client):
    from netgrip.boundary.events import EventDraft
    from netgrip.engine.engine import handles

    @handles("test.api_touch")
    async def _touch(engine, tx, cmd):
        data = {"from": "Draft", "to": "Draft", "origin": "user"}
        return [EventDraft(type="investigation.state_changed", actor="user", data=data)]

    inv = await create(app_client)
    body = {"id": str(uuid.uuid4()), "type": "test.api_touch", "node_id": None, "payload": {}}
    r1 = await app_client.post(f"/api/investigations/{inv}/commands", json=body)
    r2 = await app_client.post(f"/api/investigations/{inv}/commands", json=body)
    assert r1.status_code == r2.status_code == 202
    assert r1.json() == {"recorded": True, "duplicate": False}
    assert r2.json() == {"recorded": True, "duplicate": True}
    events = (await app_client.get(f"/api/investigations/{inv}/events?after=1")).json()
    assert len(events) == 1 and events[0]["command_id"] == body["id"]


async def test_rejected_command_is_409_with_code(app_client):
    inv = await create(app_client)
    body = {"id": str(uuid.uuid4()), "type": "warp_drive", "node_id": None, "payload": {}}
    r = await app_client.post(f"/api/investigations/{inv}/commands", json=body)
    assert r.status_code == 409
    assert r.json()["code"] == "unknown_command" and r.json()["message"]
    r = await app_client.post(f"/api/investigations/{uuid.uuid4()}/commands", json=body)
    assert r.status_code == 404


async def test_settings_response_has_no_key_material(app_client, caplog):
    caplog.set_level(logging.DEBUG)
    secret = "sk-secret-123"
    r = await app_client.put("/api/settings/keys/model", json={"value": secret})
    assert r.status_code == 200
    assert r.json()["status"] == "set" and secret not in r.text
    inv = await create(app_client)
    bodies = [
        (await app_client.get("/api/settings")).text,
        (await app_client.get(f"/api/investigations/{inv}/events")).text,
        (await app_client.get(f"/api/investigations/{inv}")).text,
        (await app_client.get("/api/investigations")).text,
    ]
    for body in bodies:
        assert secret not in body
    assert (await app_client.get("/api/settings")).json()["keys"]["model"]["set"] is True
    assert secret not in caplog.text
    assert (
        await app_client.put("/api/settings/keys/other", json={"value": "x"})
    ).status_code == 404


async def test_patch_settings_invalid_is_422(app_client):
    before = (await app_client.get("/api/settings")).json()
    for bad in ({"capacity": {"model_calls": 0}}, {"capacity": {"searches": -3}}):
        r = await app_client.patch("/api/settings", json=bad)
        assert r.status_code == 422
    assert (await app_client.get("/api/settings")).json() == before
    r = await app_client.patch("/api/settings", json={"spending_limit_usd": 7.5})
    assert r.status_code == 200 and r.json()["spending_limit_usd"] == 7.5
    inv = await create(app_client)
    row = (await app_client.get("/api/investigations")).json()[0]
    assert row["id"] == inv and row["spending_limit_usd"] == 7.5


async def test_rebuild_route(app_client):
    inv = await create(app_client)
    await create(app_client)
    db = app_client.app.state.engine.db
    async with db.tx() as tx:
        await tx.execute("UPDATE investigations SET state = 'Running' WHERE id = ?", [inv])
    r = await app_client.post("/api/system/rebuild")
    assert r.status_code == 200 and r.json() == {"replayed": 2}
    assert (await app_client.get(f"/api/investigations/{inv}")).json()["investigation"][
        "state"
    ] == "Draft"


async def test_system_pools_and_storage(app_client):
    pools = (await app_client.get("/api/system/pools")).json()
    assert pools["models"] == {"in_use": 0, "limit": 8}
    assert pools["search"] == {"in_use": 0, "limit": 4}
    assert pools["browsers"] == {
        "in_use": 0,
        "limit": 6,
        "open": 0,
        "restarts_today": 0,
        "timed_out_today": 0,
    }
    assert pools["today_usd"] == 0
    await create(app_client)
    storage = (await app_client.get("/api/system/storage")).json()
    assert storage["investigations"] == 1 and storage["pages"] == 0
    assert storage["total_bytes"] > 0 and storage["data_dir"]


async def test_delete_investigation(app_client):
    inv = await create(app_client)
    assert (await app_client.delete(f"/api/investigations/{inv}")).status_code == 204
    assert (await app_client.get("/api/investigations")).json() == []
    assert (await app_client.delete(f"/api/investigations/{inv}")).status_code == 404
