import json
import logging

import httpx
import pytest

from netgrip.adapters.search import SearchRejected, SearchUnavailable
from netgrip.adapters.search_tavily import TavilySearch

KEY = "tvly-secret-key-1234567890"


def make(handler, key=KEY):
    async def get_key():
        return key

    return TavilySearch(get_key, transport=httpx.MockTransport(handler))


def ok(results):
    return lambda req: httpx.Response(200, json={"results": results})


async def call(s, **kw):
    args = {"max_results": 5, "exclude_domains": [], "prefer": "none"} | kw
    return await s.search("great wall", **args)


async def test_maps_results_to_hits():
    s = make(
        ok(
            [
                {
                    "url": "https://a.org/x",
                    "title": "A",
                    "content": "snip",
                    "published_date": "2020-01-02",
                },
                {"url": "https://b.org/y", "title": "B", "content": "other"},
            ]
        )
    )
    hits = await call(s)
    assert [(h.url, h.title, h.snippet, h.published_at) for h in hits] == [
        ("https://a.org/x", "A", "snip", "2020-01-02"),
        ("https://b.org/y", "B", "other", None),
    ]


async def test_excluded_domains_sent_and_also_filtered_locally():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"url": "https://bad.com/p", "title": "x", "content": "x"},
                    {"url": "https://www.bad.com/q", "title": "x", "content": "x"},
                    {"url": "https://good.org/p", "title": "y", "content": "y"},
                ]
            },
        )

    hits = await call(make(handler), exclude_domains=["bad.com"])
    assert seen["exclude_domains"] == ["bad.com"]
    assert [h.url for h in hits] == ["https://good.org/p"]


async def test_primary_preference_adds_instruction():
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"results": []})

    await call(make(handler), prefer="primary")
    assert "official" in seen["query"] and seen["query"].startswith("great wall")


async def test_invalid_key_rejected():
    s = make(lambda req: httpx.Response(401, json={"detail": {"error": "Unauthorized"}}))
    with pytest.raises(SearchRejected) as e:
        await call(s)
    assert e.value.kind == "key"


async def test_quota_exhausted_rejected_credit():
    s = make(lambda req: httpx.Response(432, json={"detail": {"error": "plan usage limit"}}))
    with pytest.raises(SearchRejected) as e:
        await call(s)
    assert e.value.kind == "credit"
    s = make(
        lambda req: httpx.Response(429, json={"detail": {"error": "Your usage limit exceeded"}})
    )
    with pytest.raises(SearchRejected) as e:
        await call(s)
    assert e.value.kind == "credit"


async def test_rate_limit_429_unavailable():
    s = make(lambda req: httpx.Response(429, json={"detail": {"error": "Too many requests"}}))
    with pytest.raises(SearchUnavailable):
        await call(s)


async def test_503_unavailable():
    with pytest.raises(SearchUnavailable):
        await call(make(lambda req: httpx.Response(503)))


async def test_timeout_unavailable():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(SearchUnavailable):
        await call(make(handler))


async def test_key_not_in_logs_or_errors(caplog):
    caplog.set_level(logging.DEBUG)
    s = make(lambda req: httpx.Response(400, text=f"bad request for {KEY}"))
    with pytest.raises(SearchRejected) as e:
        await call(s)
    assert e.value.kind == "request"
    assert KEY not in str(e.value) and KEY not in e.value.message
    assert KEY not in caplog.text

    def boom(req):
        raise httpx.ConnectError(f"cannot connect with {KEY}", request=req)

    with pytest.raises(SearchUnavailable) as e2:
        await call(make(boom))
    assert KEY not in str(e2.value)


async def test_missing_key_rejected():
    s = make(ok([]), key=None)
    with pytest.raises(SearchRejected) as e:
        await call(s)
    assert e.value.kind == "key"


async def test_check_endpoint_records_verdict(tmp_path):
    from httpx import ASGITransport, AsyncClient

    from netgrip.app import create_app
    from netgrip.config import Config

    app = create_app(Config(data_dir=tmp_path))
    async with app.router.lifespan_context(app):
        engine = app.state.engine
        engine.search = TavilySearch(
            lambda: _key(engine), transport=httpx.MockTransport(lambda r: httpx.Response(401))
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            await c.put("/api/settings/keys/search", json={"value": "k"})
            r = await c.post("/api/settings/keys/search/check")
            assert r.json()["status"] == "rejected"


async def _key(engine):
    from netgrip.store.settings import get_key

    return await get_key(engine.db, "search")
