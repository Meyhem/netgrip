"""The node agent loop (domain 4.4, E5): discrete steps, each committed before the next.

`run_node(ctx)` asks `ctx.boundary()` before every step, runs one step and commits its events.
Pause and cancel are honoured only there, so the step in flight always finishes and commits.
The loop's working memory lives in `ctx.state`; calling `run_node` again with the same context
continues from the next step. A fresh context (after recovery or a rerun) starts over; the page
store, the extraction cache (D-07) and claim dedup make that repeat cheap and duplicate-free.
"""

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from netgrip.adapters.fetcher import Fetcher
from netgrip.adapters.model import ModelClient, ModelError
from netgrip.adapters.search import Search, SearchError
from netgrip.boundary.events import EventDraft
from netgrip.engine.brief import Brief, build_brief
from netgrip.engine.budget import CallContext, LimitCheck, SpendingLimitReached
from netgrip.engine.clock import Clock
from netgrip.evidence.service import EvidenceService
from netgrip.store.db import Database, Tx
from netgrip.store.pages import PageStore
from netgrip.store.projections import Publisher, append_and_project, append_and_project_in_tx
from netgrip.store.settings import ModelPrice

# The node's closed tool set (P7). Decisions name these as actions; extraction gets none.
TOOLS: tuple[str, ...] = ("search", "fetch", "record_claim", "propose_node")


class Signal(StrEnum):
    CONTINUE = "continue"
    PAUSE = "pause"
    CANCEL = "cancel"


@dataclass
class Deps:
    db: Database
    model: ModelClient
    search: Search
    fetcher: Fetcher
    pages: PageStore
    evidence: EvidenceService
    clock: Clock
    bus: Publisher | None = None
    prices: list[ModelPrice] = field(default_factory=list)
    limit_reached: LimitCheck | None = None  # the spending-limit check before model calls


@dataclass
class NodeInfo:
    id: str
    display_id: str
    kind: str
    question: str
    depth: int
    status: str
    budget: dict[str, Any]


@dataclass
class InvestigationInfo:
    id: str
    settings: dict[str, Any]


@dataclass
class NodeState:
    """Working memory of one run of the node."""

    started: bool = False
    next_step: tuple[str, Any] | None = ("plan", None)
    queries: list[str] = field(default_factory=list)
    queue: list[str] = field(default_factory=list)  # hit URLs not yet read, best first
    seen: set[str] = field(default_factory=set)  # every URL ever queued or read
    attempted: list[str] = field(default_factory=list)  # pages this node tried to read
    unobtainable: set[str] = field(default_factory=set)  # this investigation's, never re-asked
    obtained: int = 0
    claims: list[str] = field(default_factory=list)
    decisions: int = 0
    route_failures: int = 0
    excluded: set[str] = field(default_factory=set)
    note: str | None = None  # told to the next decision call (after an unusable answer)
    done: bool = False
    instructions_seen: int | None = (
        None  # applied instructions in the brief (refreshed at boundaries)
    )
    steps: int = 0  # steps run so far (a retried outage restarts its backoff after progress)


@dataclass
class NodeContext:
    node: NodeInfo
    brief: Brief
    investigation: InvestigationInfo
    deps: Deps
    boundary: Callable[[], Awaitable[Signal]] | None = None
    state: NodeState = field(default_factory=NodeState)
    call: CallContext | None = None

    def __post_init__(self) -> None:
        if self.call is None:
            self.call = CallContext(
                client=self.deps.model,
                investigation_id=self.investigation.id,
                settings=self.investigation.settings,
                prices=self.deps.prices,
                node_id=self.node.id,
                limit_reached=self.deps.limit_reached,
            )

    def draft(self, type: str, data: dict, node_id: str | None = None) -> EventDraft:
        return EventDraft(type=type, actor="node", node_id=node_id or self.node.id, data=data)

    async def emit_now(self, drafts: list[EventDraft]) -> None:
        """Commit `drafts` alone (activities): the step's spend stays with its results."""
        await append_and_project(self.deps.db, self.investigation.id, drafts, self.deps.bus)

    async def commit(
        self, drafts: list[EventDraft], extra: Callable[[Tx], Awaitable[None]] | None = None
    ) -> None:
        """Commit the step's results with its pending spend in one transaction. On failure
        nothing is written and the spend stays pending."""
        pending, self.call.pending_events = self.call.pending_events, []
        try:
            async with self.deps.db.tx() as tx:
                if extra is not None:
                    await extra(tx)
                await append_and_project_in_tx(
                    tx, self.investigation.id, [*pending, *drafts], self.deps.bus
                )
        except BaseException:
            self.call.pending_events = [*pending, *self.call.pending_events]
            raise


async def node_context(
    deps: Deps,
    investigation_id: str,
    node_id: str,
    boundary: Callable[[], Awaitable[Signal]] | None = None,
) -> NodeContext:
    db = deps.db
    n = (await db.read("SELECT * FROM nodes WHERE id = ?", [node_id]))[0]
    inv = (await db.read("SELECT settings FROM investigations WHERE id = ?", [investigation_id]))[0]
    node = NodeInfo(
        id=n["id"], display_id=n["display_id"], kind=n["kind"], question=n["question"],
        depth=n["depth"], status=n["status"], budget=json.loads(n["budget"] or "{}"),
    )  # fmt: skip
    ctx = NodeContext(
        node=node,
        brief=await build_brief(db, node_id, deps.evidence),
        investigation=InvestigationInfo(investigation_id, json.loads(inv["settings"])),
        deps=deps,
        boundary=boundary,
    )
    # Known gap of the page store: an unobtainable URL is not remembered, so remember it here.
    rows = await db.read(
        "SELECT data FROM events WHERE investigation_id = ? AND type = 'page.unobtainable'",
        [investigation_id],
    )
    ctx.state.unobtainable = {json.loads(r["data"])["url"] for r in rows}
    if node.status == "Waiting on children":
        ctx.state.started = True
        ctx.state.next_step = ("aggregate", None)
    return ctx


async def run_node(ctx: NodeContext) -> None:
    """Run steps until the node completes, fails, waits on children, or the boundary says
    pause or cancel. Provider outages and rejections propagate (the runtime pauses, N-05)
    after the spend already paid for is committed."""
    from netgrip.engine import steps

    state = ctx.state
    if ctx.node.status in ("Completed", "Failed", "Rejected"):
        return
    try:
        if not state.started:
            rows = await ctx.deps.db.read(
                "SELECT COUNT(*) AS n FROM events WHERE investigation_id = ? AND node_id = ?"
                " AND type = 'node.started'",
                [ctx.investigation.id, ctx.node.id],
            )
            data = {"attempt": rows[0]["n"] + 1, "brief": ctx.brief.model_dump(mode="json")}
            await ctx.emit_now([ctx.draft("node.started", data)])
            state.started = True
        while state.next_step is not None and not state.done:
            if ctx.boundary is not None and await ctx.boundary() != Signal.CONTINUE:
                return
            name, arg = state.next_step
            state.next_step = await steps.STEPS[name](ctx, arg)
            state.steps += 1
    except (ModelError, SearchError, SpendingLimitReached):
        if ctx.call.pending_events:
            await ctx.commit([])
        raise
