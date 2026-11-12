import json
import logging
from decimal import Decimal

import httpx
import pytest

from netgrip.adapters.fakes import FakeModelClient
from netgrip.adapters.model import (
    Message,
    ModelMalformed,
    ModelRejected,
    ModelRequest,
    ModelUnavailable,
)
from netgrip.adapters.model_openai import OpenAICompatClient, check_model_key
from netgrip.store.settings import set_key

SECRET = "sk-very-secret-key-123"
SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"],
}


def req(**kw) -> ModelRequest:
    base = dict(
        purpose="plan.initial",
        tier="strong",
        model="anthropic/claude-opus-5.5",
        system="You plan.",
        messages=[Message(role="user", content="Is it visible?")],
    )
    return ModelRequest(**(base | kw))


def completion(content: str, usage: dict | None = None) -> dict:
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
    }


def client_for(handler, key: str | None = SECRET) -> OpenAICompatClient:
    async def get_key():
        return key

    return OpenAICompatClient(
        "https://models.test/v1", get_key, transport=httpx.MockTransport(handler)
    )


async def test_cost_taken_from_provider_when_present():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0123}
        return httpx.Response(200, json=completion('{"answer": "no"}', usage))

    resp = await client_for(handler).complete(req(response_schema=SCHEMA))
    assert seen["url"] == "https://models.test/v1/chat/completions"
    assert seen["auth"] == f"Bearer {SECRET}"
    assert seen["body"]["model"] == "anthropic/claude-opus-5.5"
    assert seen["body"]["messages"][0] == {"role": "system", "content": "You plan."}
    assert resp.parsed == {"answer": "no"}
    assert (resp.usage.tokens_in, resp.usage.tokens_out) == (10, 5)
    assert resp.usage.cost_usd == Decimal("0.0123")


async def test_cost_is_none_when_provider_gives_none():
    resp = await client_for(lambda r: httpx.Response(200, json=completion("hi"))).complete(req())
    assert resp.usage.cost_usd is None
    assert resp.text == "hi"


async def test_tool_calls_are_parsed():
    body = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "search", "arguments": '{"q": "wall"}'},
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }
    resp = await client_for(lambda r: httpx.Response(200, json=body)).complete(req())
    assert [(c.id, c.name, c.arguments) for c in resp.tool_calls] == [
        ("c1", "search", {"q": "wall"})
    ]


async def test_401_raises_rejected_key():
    client = client_for(lambda r: httpx.Response(401, json={"error": {"message": "bad key"}}))
    with pytest.raises(ModelRejected) as e:
        await client.complete(req())
    assert e.value.kind == "key"


async def test_missing_key_raises_rejected_key():
    client = client_for(lambda r: httpx.Response(200, json=completion("x")), key=None)
    with pytest.raises(ModelRejected) as e:
        await client.complete(req())
    assert e.value.kind == "key"


async def test_402_raises_rejected_credit():
    client = client_for(lambda r: httpx.Response(402, json={"error": {"message": "no credit"}}))
    with pytest.raises(ModelRejected) as e:
        await client.complete(req())
    assert e.value.kind == "credit"


@pytest.mark.parametrize("status", [429, 503])
async def test_429_and_503_raise_unavailable(status):
    client = client_for(lambda r: httpx.Response(status))
    with pytest.raises(ModelUnavailable):
        await client.complete(req())


async def test_timeout_raises_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ModelUnavailable):
        await client_for(handler).complete(req())


async def test_schema_violation_raises_malformed():
    client = client_for(lambda r: httpx.Response(200, json=completion('{"wrong": 1}')))
    with pytest.raises(ModelMalformed):
        await client.complete(req(response_schema=SCHEMA))


async def test_non_json_with_schema_raises_malformed():
    client = client_for(lambda r: httpx.Response(200, json=completion("not json")))
    with pytest.raises(ModelMalformed):
        await client.complete(req(response_schema=SCHEMA))


async def test_malformed_answer_carries_usage():
    usage = {"prompt_tokens": 12, "completion_tokens": 8, "cost": 0.05}
    for content in ('{"wrong": 1}', "not json"):
        client = client_for(lambda r, c=content: httpx.Response(200, json=completion(c, usage)))
        with pytest.raises(ModelMalformed) as exc:
            await client.complete(req(response_schema=SCHEMA))
        assert exc.value.usage is not None
        assert (exc.value.usage.tokens_in, exc.value.usage.tokens_out) == (12, 8)
        assert exc.value.usage.cost_usd == Decimal("0.05")


async def test_malformed_streamed_answer_carries_usage():
    body = (
        'data: {"choices": [{"delta": {"content": "not json"}}]}\n\n'
        'data: {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}\n\n'
        "data: [DONE]\n\n"
    )
    client = client_for(lambda r: httpx.Response(200, text=body))
    with pytest.raises(ModelMalformed) as exc:
        async for _ in client.stream(req(response_schema=SCHEMA)):
            pass
    assert (exc.value.usage.tokens_in, exc.value.usage.tokens_out) == (3, 2)


async def test_fake_checks_schema_and_reports_usage():
    fake = FakeModelClient({"plan.initial": [{"parsed": {"wrong": 1}}, {"raise": "malformed"}]})
    with pytest.raises(ModelMalformed) as exc:
        await fake.complete(req(response_schema=SCHEMA))
    assert exc.value.usage is not None and exc.value.usage.cost_usd == Decimal("0.01")
    with pytest.raises(ModelMalformed) as exc:
        await fake.complete(req(response_schema=SCHEMA))
    assert exc.value.usage is None


async def test_key_never_logged(caplog):
    caplog.set_level(logging.DEBUG)
    ok = client_for(lambda r: httpx.Response(200, json=completion("hi")))
    await ok.complete(req())
    bad = client_for(lambda r: httpx.Response(401))
    with pytest.raises(ModelRejected) as e:
        await bad.complete(req())
    assert SECRET not in caplog.text
    assert SECRET not in str(e.value)
    assert SECRET not in repr(ok.__dict__)


async def test_stream_yields_text_then_response():
    sse = (
        'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n'
        'data: {"choices":[{"delta":{"content":"lo"}}]}\n\n'
        'data: {"choices":[],"usage":{"prompt_tokens":3,"completion_tokens":2,"cost":0.5}}\n\n'
        "data: [DONE]\n\n"
    )
    client = client_for(lambda r: httpx.Response(200, content=sse.encode()))
    items = [i async for i in client.stream(req())]
    assert items[:2] == ["Hel", "lo"]
    assert items[2].text == "Hello"
    assert items[2].usage.cost_usd == Decimal("0.5")


async def test_check_model_key_valid_and_rejected():
    paths = []

    def ok(request):
        paths.append((request.method, request.url.path))
        return httpx.Response(200, json={"data": []})

    status = await check_model_key(client_for(ok))
    assert paths == [("GET", "/v1/models")]
    assert status.status == "set" and status.checked_at

    status = await check_model_key(client_for(lambda r: httpx.Response(401)))
    assert status.status == "rejected"


async def test_fake_serves_script_in_order_and_records_calls():
    fake = FakeModelClient(
        {
            "plan.initial": [{"parsed": {"n": 1}}],
            "plan.replan": [{"parsed": {"n": 2}}, {"raise": "unavailable"}, {"text": "three"}],
        }
    )
    a = req()
    b = req(purpose="plan.replan")
    assert (await fake.complete(a)).parsed == {"n": 1}
    assert (await fake.complete(b)).parsed == {"n": 2}
    with pytest.raises(ModelUnavailable):
        await fake.complete(b)
    assert (await fake.complete(b)).text == "three"
    with pytest.raises(LookupError):
        await fake.complete(b)
    assert [c.purpose for c in fake.calls] == [
        "plan.initial",
        "plan.replan",
        "plan.replan",
        "plan.replan",
        "plan.replan",
    ]


async def test_fake_keys_on_node_ref_when_scripted_and_repeats_last():
    fake = FakeModelClient(
        {"x": [{"text": "generic"}], "x:D1": [{"text": "for D1"}]}, repeat_last=True
    )
    assert (await fake.complete(req(purpose="x", node_ref="D1"))).text == "for D1"
    assert (await fake.complete(req(purpose="x", node_ref="D2"))).text == "generic"
    assert (await fake.complete(req(purpose="x", node_ref="D2"))).text == "generic"


async def test_great_wall_scenario_has_required_shape():
    fake = FakeModelClient.from_scenario("great_wall")
    first = (await fake.complete(req())).parsed
    assert [p["ref"] for p in first["premises"]] == ["P1"]
    refs = {n["ref"] for n in first["nodes"]}
    replan = [(await fake.complete(req(purpose="plan.replan"))).parsed for _ in range(3)]
    new = {n["ref"] for n in replan[0]["nodes"]}
    assert len(new - refs) == 2 and len(refs - new) == 1


async def test_model_key_check_endpoint(app_client):
    engine = app_client.app.state.engine
    await set_key(engine.db, "model", SECRET)

    async def get_key():
        return SECRET

    engine.model_client = OpenAICompatClient(
        "https://models.test/v1",
        get_key,
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"data": []})),
    )
    r = await app_client.post("/api/settings/keys/model/check")
    assert r.status_code == 200
    assert r.json()["status"] == "set" and r.json()["checked_at"]
    assert SECRET not in r.text

    engine.model_client = OpenAICompatClient(
        "https://models.test/v1",
        get_key,
        transport=httpx.MockTransport(lambda r: httpx.Response(401)),
    )
    r = await app_client.post("/api/settings/keys/model/check")
    assert r.json()["status"] == "rejected"
    assert (await app_client.get("/api/settings")).json()["keys"]["model"]["status"] == "rejected"


async def test_fake_mode_wires_fake_client_and_valid_key(tmp_path):
    from netgrip.app import create_app
    from netgrip.config import Config

    app = create_app(Config(data_dir=tmp_path / "d", fake=True))
    async with app.router.lifespan_context(app):
        engine = app.state.engine
        assert isinstance(engine.model_client, FakeModelClient)
        assert engine.model_client.repeat_last is True
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.post("/api/settings/keys/model/check")
            assert r.json()["status"] == "set"
