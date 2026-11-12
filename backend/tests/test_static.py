import httpx
import pytest

from netgrip.app import create_app


@pytest.fixture
async def client(config, tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Netgrip</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("outside")
    app = create_app(config, frontend_dist=dist)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_single_page_fallback(client):
    for path in ("/", "/investigations/abc", "/settings"):
        r = await client.get(path)
        assert r.status_code == 200
        assert "<title>Netgrip</title>" in r.text
        assert r.headers["content-type"].startswith("text/html")


async def test_assets_served(client):
    r = await client.get("/assets/app.js")
    assert r.status_code == 200 and r.text == "console.log(1)"


async def test_api_unknown_is_json_404(client):
    r = await client.get("/api/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert (await client.get("/api/health")).json() == {"status": "ok"}


async def test_no_escape_from_dist(client):
    r = await client.get("/..%2fsecret.txt")
    assert "outside" not in r.text
