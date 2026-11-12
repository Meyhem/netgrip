import pytest

from netgrip.engine.estimate import estimate
from netgrip.store.settings import Effort, ModelPrice

MEDIUM = Effort(max_depth=4, max_nodes=40, sources_per_node=8, parallel=4, sources_to_confirm=2)
MODELS = [
    ModelPrice(id="a/strong", price_in_per_m=15, price_out_per_m=75),
    ModelPrice(id="a/standard", price_in_per_m=3, price_out_per_m=15),
    ModelPrice(id="a/fast", price_in_per_m=1, price_out_per_m=5),
    ModelPrice(id="b/verifier", price_in_per_m=2, price_out_per_m=8),
    ModelPrice(id="c/unpriced"),
]
TIERS = {"strong": "a/strong", "standard": "a/standard", "fast": "a/fast", "verifier": "b/verifier"}


def test_estimate_is_a_range_low_below_high():
    e = estimate(MEDIUM, TIERS, MODELS)
    assert 0 < e.low_usd < e.high_usd
    assert e.low_usd == pytest.approx(0.4 * e.high_usd)
    # strong: 40 nodes × (6000 in × $15 + 1500 out × $75) per million
    assert e.per_tier["strong"].high_usd == pytest.approx(40 * (6000 * 15 + 1500 * 75) / 1e6)
    # fast is per source
    assert e.per_tier["fast"].high_usd == pytest.approx(40 * 8 * (8000 * 1 + 800 * 5) / 1e6)
    for r in e.per_tier.values():
        assert r.low_usd == pytest.approx(0.4 * r.high_usd)
    assert e.high_usd == pytest.approx(sum(r.high_usd for r in e.per_tier.values()))
    assert e.unpriced_models == []


def test_unpriced_model_listed():
    e = estimate(MEDIUM, TIERS | {"verifier": "c/unpriced", "fast": "not/known"}, MODELS)
    assert e.unpriced_models == ["not/known", "c/unpriced"]  # tier order
    assert e.per_tier["verifier"].high_usd == 0


def test_shares_sum_to_one():
    e = estimate(MEDIUM, TIERS, MODELS)
    assert sum(r.share for r in e.per_tier.values()) == pytest.approx(1)
    assert set(e.per_tier) == {"strong", "standard", "fast", "verifier"}


async def test_estimate_endpoint(app_client):
    r = await app_client.post("/api/estimate", json={"effort": "Medium"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["low_usd"] < body["high_usd"]
    assert body["unpriced_models"] == ["openai/gpt-5.2"]
    r = await app_client.post(
        "/api/estimate", json={"effort": "Low", "tiers": {"verifier": "anthropic/claude-haiku-5.5"}}
    )
    assert r.json()["unpriced_models"] == []
    assert (await app_client.post("/api/estimate", json={"effort": "Huge"})).status_code == 422
