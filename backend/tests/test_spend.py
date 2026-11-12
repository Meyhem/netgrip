from decimal import Decimal

import pytest

from netgrip.adapters.fakes import FakeModelClient
from netgrip.adapters.model import Message, ModelRequest
from netgrip.boundary.events import EventDraft
from netgrip.engine.budget import CallContext, call_model
from netgrip.store.db import open_db
from netgrip.store.projections import append_and_project
from netgrip.store.rebuild import rebuild
from netgrip.store.settings import DEFAULT_SETTINGS, SettingsModel, resolve_investigation_settings

INV = "inv-1"


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


def glob():
    return SettingsModel.model_validate(DEFAULT_SETTINGS)


def ctx_for(client, node_id=None, prices=None):
    g = glob()
    return CallContext(
        client=client,
        investigation_id=INV,
        settings=resolve_investigation_settings(g, {}),
        prices=prices if prices is not None else g.models,
        node_id=node_id,
    )


def req(tier="standard"):
    return ModelRequest(
        purpose="plan.initial", tier=tier, model="ignored", system="s",
        messages=[Message(role="user", content="hi")],
    )  # fmt: skip


async def seed(db):
    await append_and_project(
        db,
        INV,
        [
            EventDraft(
                type="investigation.created",
                actor="user",
                data={"prompt": "p", "settings": {"spending_limit_usd": 5.0}},
            )
        ],
    )


def client(usage):
    usage = {"cost_usd": None} | usage  # the fake defaults to a provider cost
    return FakeModelClient({"plan.initial": [{"text": "ok", "usage": usage}] * 5})


async def test_spend_priced_from_table_when_provider_gives_none():
    c = client({"tokens_in": 1_000_000, "tokens_out": 100_000})
    ctx = ctx_for(c)
    await call_model(ctx, req("standard"))
    [draft] = ctx.pending_events
    assert draft.type == "spend.recorded"
    # balanced: standard = SONNET, 3.0 in / 15.0 out per million tokens
    assert Decimal(draft.data["amount_usd"]) == Decimal("4.5")
    assert draft.data["approximate"] is False
    assert draft.data["model"] == "anthropic/claude-sonnet-5.5"
    assert draft.data["tier"] == "standard"
    assert (draft.data["tokens_in"], draft.data["tokens_out"]) == (1_000_000, 100_000)
    assert c.calls[0].model == "anthropic/claude-sonnet-5.5"


async def test_provider_cost_wins_and_node_id_is_carried():
    c = client({"tokens_in": 10, "tokens_out": 10, "cost_usd": "0.25"})
    ctx = ctx_for(c, node_id="n1")
    await call_model(ctx, req())
    [draft] = ctx.pending_events
    assert Decimal(draft.data["amount_usd"]) == Decimal("0.25")
    assert draft.data["approximate"] is False
    assert draft.node_id == "n1"


async def test_unknown_price_marks_approximate():
    ctx = ctx_for(client({"tokens_in": 500, "tokens_out": 500}))
    await call_model(ctx, req("verifier"))  # GPT: no price
    [draft] = ctx.pending_events
    assert Decimal(draft.data["amount_usd"]) == 0
    assert draft.data["approximate"] is True


async def test_spend_accumulates_on_investigation(db):
    await seed(db)
    ctx = ctx_for(client({"tokens_in": 1_000_000, "tokens_out": 0}))
    await call_model(ctx, req())
    await call_model(ctx, req())
    ctx2 = ctx_for(client({"tokens_in": 1, "tokens_out": 1}))
    await call_model(ctx2, req("verifier"))
    await append_and_project(db, INV, ctx.pending_events + ctx2.pending_events)
    [row] = await db.read("SELECT spent_usd, spend_approximate FROM investigations")
    assert row["spent_usd"] == pytest.approx(6.0)
    assert row["spend_approximate"] == 1
    await rebuild(db)
    [row] = await db.read("SELECT spent_usd, spend_approximate FROM investigations")
    assert row["spent_usd"] == pytest.approx(6.0)
    assert row["spend_approximate"] == 1


async def test_spend_in_snapshot_and_list(app_client):
    import uuid

    eng = app_client.app.state.engine
    iid = str(uuid.uuid4())
    await eng.create_investigation(uuid.UUID(iid), "p", {})
    ctx = ctx_for(client({"tokens_in": 1_000_000, "tokens_out": 0}))
    ctx.investigation_id = iid
    await call_model(ctx, req())
    await append_and_project(eng.db, iid, ctx.pending_events)
    snap = (await app_client.get(f"/api/investigations/{iid}")).json()
    assert snap["investigation"]["spent_usd"] == pytest.approx(3.0)
    [row] = (await app_client.get("/api/investigations")).json()
    assert row["spent_usd"] == pytest.approx(3.0)
