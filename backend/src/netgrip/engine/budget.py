"""The spend ledger: every model call goes through `call_model` and leaves a `spend.recorded`."""

from dataclasses import dataclass, field
from decimal import Decimal

from netgrip.adapters.model import ModelClient, ModelRequest, ModelResponse, Usage
from netgrip.boundary.events import EventDraft
from netgrip.store.settings import ModelPrice

MILLION = Decimal(1_000_000)


@dataclass
class CallContext:
    """What a step needs to call models. `pending_events` collects the step's `spend.recorded`
    drafts; the caller commits them in the same transaction as the step's results (R4)."""

    client: ModelClient
    investigation_id: str
    settings: dict  # the investigation's resolved settings: `tiers` maps tier -> model id
    prices: list[ModelPrice]  # price table from the global settings, per million tokens
    node_id: str | None = None
    pending_events: list[EventDraft] = field(default_factory=list)


def price_usage(usage: Usage, model: str, prices: list[ModelPrice]) -> tuple[Decimal, bool]:
    """(amount, approximate): the provider's cost, else tokens x table price, else 0 approximate."""
    if usage.cost_usd is not None:
        return usage.cost_usd, False
    price = next((p for p in prices if p.id == model), None)
    if price is None or price.price_in_per_m is None or price.price_out_per_m is None:
        return Decimal(0), True
    amount = (
        usage.tokens_in * Decimal(str(price.price_in_per_m))
        + usage.tokens_out * Decimal(str(price.price_out_per_m))
    ) / MILLION
    return amount, False


async def call_model(ctx: CallContext, req: ModelRequest) -> ModelResponse:
    """Call the model assigned to `req.tier` and record the spend in `ctx.pending_events`.

    Opens no transaction. A call that raises records nothing."""
    model = ctx.settings["tiers"][req.tier]
    req = req.model_copy(update={"model": model})
    resp = await ctx.client.complete(req)
    amount, approximate = price_usage(resp.usage, model, ctx.prices)
    ctx.pending_events.append(
        EventDraft(
            type="spend.recorded",
            actor="node" if ctx.node_id else "orchestrator",
            node_id=ctx.node_id,
            data={
                "tier": req.tier,
                "model": model,
                "amount_usd": str(amount),
                "approximate": approximate,
                "tokens_in": resp.usage.tokens_in,
                "tokens_out": resp.usage.tokens_out,
            },
        )
    )
    return resp
