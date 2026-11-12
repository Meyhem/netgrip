"""Rough cost range for an investigation before it runs. An estimate, not a quote."""

from pydantic import BaseModel

from netgrip.store.settings import Effort, ModelPrice, Tier

# Tokens (in, out) per node for each tier; Fast is per source read. Placeholders, to be tuned
# against real runs with the effort values (D-20).
TOKENS_PER_NODE: dict[Tier, tuple[int, int]] = {
    "strong": (6000, 1500),
    "standard": (30000, 4000),
    "fast": (8000, 800),
    "verifier": (3000, 500),
}
TIERS: tuple[Tier, ...] = ("strong", "standard", "fast", "verifier")
LOW_FACTOR = 0.4


class TierRange(BaseModel):
    low_usd: float
    high_usd: float
    share: float


class Estimate(BaseModel):
    low_usd: float
    high_usd: float
    per_tier: dict[Tier, TierRange]
    unpriced_models: list[str]


def estimate(effort: Effort, tiers: dict[str, str], models: list[ModelPrice]) -> Estimate:
    prices = {m.id: m for m in models}
    highs: dict[Tier, float] = {}
    unpriced: list[str] = []
    for tier in TIERS:
        model_id = tiers[tier]
        m = prices.get(model_id)
        if m is None or m.price_in_per_m is None or m.price_out_per_m is None:
            if model_id not in unpriced:
                unpriced.append(model_id)
            highs[tier] = 0.0
            continue
        calls = effort.max_nodes * (effort.sources_per_node if tier == "fast" else 1)
        tok_in, tok_out = TOKENS_PER_NODE[tier]
        highs[tier] = calls * (tok_in * m.price_in_per_m + tok_out * m.price_out_per_m) / 1e6
    total = sum(highs.values())
    per_tier = {
        t: TierRange(low_usd=LOW_FACTOR * h, high_usd=h, share=h / total if total else 0.0)
        for t, h in highs.items()
    }
    return Estimate(
        low_usd=LOW_FACTOR * total, high_usd=total, per_tier=per_tier, unpriced_models=unpriced
    )
