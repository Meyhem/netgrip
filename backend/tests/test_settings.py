import pytest
from pydantic import ValidationError

from netgrip.store.db import open_db
from netgrip.store.settings import (
    DEFAULT_SETTINGS,
    get_key,
    get_settings,
    key_status,
    mark_key,
    patch_settings,
    set_key,
)


@pytest.fixture
async def db(tmp_path):
    d = await open_db(tmp_path / "n.sqlite")
    yield d
    await d.close()


async def test_defaults_match_overview(db):
    s = await get_settings(db)
    medium = s.effort["Medium"]
    assert (medium.max_depth, medium.max_nodes, medium.sources_per_node) == (4, 40, 8)
    assert (medium.parallel, medium.sources_to_confirm) == (4, 2)
    low, high = s.effort["Low"], s.effort["High"]
    assert (low.max_depth, low.max_nodes, low.sources_per_node, low.parallel) == (2, 12, 4, 2)
    assert low.sources_to_confirm == 1
    assert (high.max_depth, high.max_nodes, high.sources_per_node, high.parallel) == (6, 80, 12, 6)
    assert high.sources_to_confirm == 3
    assert s.default_effort == "Medium"
    assert f"{s.spending_limit_usd:.2f}" == "5.00"
    assert s.retry_before_pause_seconds == 300
    assert s.page_reuse == "1d"
    assert s.politeness_seconds == 2
    cap = s.capacity
    assert (cap.investigations, cap.model_calls, cap.searches, cap.browser_pages) == (5, 8, 4, 6)
    assert s.model_endpoint == "https://openrouter.ai/api/v1"
    assert s.default_preset == "balanced"
    assert set(s.presets) == {"economy", "balanced", "maximum"}
    assert set(s.presets["balanced"]) == {"strong", "standard", "fast", "verifier"}
    assert s.excluded_domains == []
    assert s.model_dump(mode="json") == DEFAULT_SETTINGS


async def test_patch_persists(db):
    await patch_settings(db, {"spending_limit_usd": 12.5, "capacity": {"searches": 2}})
    s = await get_settings(db)
    assert s.spending_limit_usd == 12.5
    assert s.capacity.searches == 2
    assert s.capacity.model_calls == 8  # untouched siblings keep their values
    await patch_settings(db, {"page_reuse": "always_refetch"})
    assert (await get_settings(db)).page_reuse == "always_refetch"


@pytest.mark.parametrize(
    "partial",
    [
        {"capacity": {"browser_pages": 0}},
        {"capacity": {"model_calls": -1}},
        {"spending_limit_usd": 0},
        {"effort": {"Medium": {"max_nodes": -5}}},
        {"no_such_setting": 1},
        {"default_preset": "lavish"},
        {"page_reuse": "1w"},
    ],
)
async def test_invalid_patch_rejected_and_unchanged(db, partial):
    before = await get_settings(db)
    with pytest.raises(ValidationError):
        await patch_settings(db, partial)
    assert await get_settings(db) == before


async def test_key_status_never_contains_value(db):
    assert (await key_status(db, "model")).status == "none"
    await set_key(db, "model", "sk-secret-123")
    status = await key_status(db, "model")
    assert status.set and status.status == "set"
    assert "sk-secret-123" not in status.model_dump_json()
    assert await get_key(db, "model") == "sk-secret-123"
    await mark_key(db, "model", "rejected", "invalid key")
    status = await key_status(db, "model")
    assert status.status == "rejected" and status.checked_at is not None
    assert "sk-secret-123" not in status.model_dump_json()
    assert await get_key(db, "search") is None


async def test_available_models_in_fake_mode_is_empty_list(tmp_path):
    import httpx

    from netgrip.app import create_app
    from netgrip.config import Config

    app = create_app(Config(data_dir=tmp_path / "data", fake=True))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            r = await client.get("/api/settings/models/available")
    assert r.status_code == 200
    assert r.json() == []
