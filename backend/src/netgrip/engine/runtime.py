"""One runtime per active investigation (D-04): in-process asyncio tasks that run up to
`effort.parallel` eligible nodes, check each result with the orchestrator, and conclude.

The loop: load the graph, schedule, start nodes into free slots, wait for one to return or a
request (pause, stop), repeat. When nothing runs and nothing is eligible the orchestrator
decides (O3); "conclude" hands over to synthesis.

Pause and stop act at step boundaries only: the node's `boundary` says pause or cancel, its
step in flight finishes and commits, and its `NodeContext` is kept, so resume continues the
node from its next step. A paused investigation enters Paused once nothing is in flight.

Hooks for later tasks:
System pauses (Task 7, N-05, B4):
- An outage (ModelUnavailable, SearchUnavailable) in a node is retried with delays 1, 2, 4 ...
  capped at 30 s, within the "retry before pausing" setting, shown as `Retrying` on the node.
  Then the investigation pauses (origin system). The node keeps its context: its interrupted
  step was not committed, so it runs again on resume (no reset event).
- A rejected key or exhausted credit pauses at once; a rejected key is marked on the key.
- Before every step (and before starting nodes or asking the orchestrator) the spend is
  checked: at or over the limit, nothing more is called and the investigation pauses with
  cause `spending_limit`. Spend is committed with each step, so checking at step boundaries
  is checking before every model call that could see new spend.
- `start()` on an investigation whose nodes were reset by recovery (Task 8) just schedules
  them: a fresh context starts the node over.
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from netgrip.adapters.model import ModelError, ModelRejected, ModelUnavailable
from netgrip.adapters.search import SearchError, SearchRejected, SearchUnavailable
from netgrip.boundary.events import EventDraft
from netgrip.engine import orchestrator
from netgrip.engine.agent import Deps, NodeContext, Signal, node_context, run_node
from netgrip.engine.clock import SystemClock
from netgrip.engine.orchestrator import OrchestratorContext
from netgrip.engine.scheduler import GraphNode, Schedule, load_graph, schedule
from netgrip.engine.synthesis import synthesise
from netgrip.evidence.service import EvidenceService
from netgrip.store.pages import PageStore
from netgrip.store.projections import append_and_project, append_and_project_in_tx
from netgrip.store.settings import get_settings, mark_key

if TYPE_CHECKING:
    from netgrip.engine.engine import Engine

log = logging.getLogger(__name__)

MAX_DELAY = 30.0


def backoff_delays(limit: float) -> list[float]:
    """1, 2, 4, 8 ... capped at 30 s, as many as fit in `limit` seconds in total."""
    out: list[float] = []
    total, d = 0.0, 1.0
    while total + d <= limit:
        out.append(d)
        total += d
        d = min(d * 2, MAX_DELAY)
    return out


class InvestigationRuntime:
    def __init__(self, engine: "Engine", investigation_id: str) -> None:
        self.engine = engine
        self.id = investigation_id
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._ctxs: dict[str, NodeContext] = {}  # kept across pause and stop
        self._suspended: list[str] = []  # returned at a boundary; continue these first
        self._pause: tuple[str, str | None, str] | None = None
        self._stopping = False
        self._wake = asyncio.Event()
        self._loop: asyncio.Task[None] | None = None
        self._last_schedule: tuple | None = None
        self._deps: Deps | None = None
        self._octx: OrchestratorContext | None = None
        self._gen = 0  # bumped by every (re)launch; a pause write from an older one is dropped
        self._retry_limit = 300.0

    # --- control -----------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._loop is not None and not self._loop.done()

    async def start(self) -> None:
        """Start (or continue) the loop. Creates a task only, so it is safe in after_commit."""
        self._launch()

    def _launch(self) -> None:
        self._gen += 1
        self._stopping = False
        self._pause = None
        if self.active:  # still draining a pause or stop: keep this loop going
            self._wake.set()
            return
        self._loop = asyncio.create_task(self._run(), name=f"runtime:{self.id}")

    def resume(self) -> None:
        self._launch()

    def request_pause(self, cause: str, detail: str | None = None, origin: str = "user") -> None:
        """No new step starts; running steps finish; then Paused with this cause."""
        if self._pause is None:
            self._pause = (cause, detail, origin)
        self._wake.set()

    def request_stop(self) -> None:
        """Like a pause, without a state change (the stop command already recorded Stopped)."""
        self._stopping = True
        self._wake.set()

    @property
    def pausing(self) -> bool:
        return self.active and self._pause is not None

    async def stop(self, abandon: bool = False) -> None:
        """Let running steps finish (or, with `abandon`, cancel them: an uncommitted step is
        simply lost and runs again later), then end the loop."""
        self.request_stop()
        if abandon:
            for t in self._tasks.values():
                t.cancel()
            if self._loop is not None:
                self._loop.cancel()
        await self.wait()

    async def wait(self) -> None:
        """Until the loop ends (Completed, Paused, Stopped)."""
        if self._loop is not None:
            await asyncio.gather(self._loop, return_exceptions=True)

    # --- the loop ----------------------------------------------------------------------------

    async def _setup(self) -> None:
        if self._deps is not None:
            return
        e = self.engine
        glob = await get_settings(e.db)
        prices = glob.models
        self._retry_limit = float(glob.retry_before_pause_seconds)
        evidence = EvidenceService(e.db, e.bus)
        clock = e.clock or SystemClock()
        self._deps = Deps(
            db=e.db, model=e.model_client, search=e.search, fetcher=e.fetcher,
            pages=e.pages or PageStore(e.db, e.config.data_dir), evidence=evidence,
            clock=clock, bus=e.bus, prices=prices,
        )  # fmt: skip
        self._octx = OrchestratorContext(
            self.id, e.db, e.model_client, evidence, clock, e.bus, prices
        )

    async def _state(self) -> str:
        rows = await self.engine.db.read("SELECT state FROM investigations WHERE id = ?", [self.id])
        return rows[0]["state"] if rows else ""

    async def _parallel(self) -> int:
        rows = await self.engine.db.read(
            "SELECT settings FROM investigations WHERE id = ?", [self.id]
        )
        return int(json.loads(rows[0]["settings"])["effort_budget"]["parallel"])

    async def _mark_planned_coordinators(self) -> None:
        """A planned node with included children is a coordinator from the start: it waits on
        them and then aggregates (G3), instead of running as a leaf."""
        rows = await self.engine.db.read(
            "SELECT n.id FROM nodes n WHERE n.investigation_id = ? AND n.status = 'Pending'"
            " AND n.parent_id IS NOT NULL AND EXISTS (SELECT 1 FROM nodes c WHERE"
            " c.parent_id = n.id AND c.inclusion = 'Included' AND c.status != 'Proposed')",
            [self.id],
        )
        if rows:
            drafts = [
                EventDraft(type="node.waiting_on_children", actor="orchestrator",
                           node_id=r["id"], data={})
                for r in rows
            ]  # fmt: skip
            await append_and_project(self.engine.db, self.id, drafts, self.engine.bus)

    async def _run(self) -> None:
        try:
            await self._setup()
            await self._mark_planned_coordinators()
            parallel = await self._parallel()
            while True:
                if self._stopping or self._pause is not None:
                    if not self._tasks:
                        if not self._stopping:
                            await self._enter_paused(self._pause)
                        if self._stopping or self._pause is not None:
                            return
                        continue  # resumed while draining
                else:
                    if await self._state() == "Running" and await self._limit_reached():
                        self._request_limit_pause()
                        continue
                    if await self._state() != "Running":
                        if not self._tasks:
                            return
                    else:
                        free = parallel - len(self._tasks)
                        while free > 0 and self._suspended:
                            self._start_node(self._suspended.pop(0))
                            free -= 1
                        sched = schedule(await self._graph(), max(free, 0))
                        await self._emit_schedule(sched)
                        for nid in sched.order[: max(free, 0)]:
                            self._start_node(nid)
                        if not self._tasks:
                            if await orchestrator.decide_next(self._octx) == "conclude":
                                await synthesise(self.engine, self.id)
                                return
                            continue
                await self._wait_any()
        except asyncio.CancelledError:
            for t in self._tasks.values():
                t.cancel()
            raise
        except (ModelError, SearchError) as e:
            # An orchestrator call in the loop hit the provider: pause the system way.
            log.warning("runtime of %s: provider error in the loop (%s)", self.id, e)
            try:
                await self._mark_rejected_key(e)
                await self._enter_paused((self._cause(e), str(e), "system"))
            except Exception:
                log.exception("runtime of %s: could not record the system pause", self.id)
        except Exception:
            # Not a provider problem: log it; the investigation stays Running and `resume`
            # restarts this runtime (the resume handler accepts Running with no live loop).
            log.exception("runtime of %s failed", self.id)

    async def _graph(self) -> list[GraphNode]:
        busy = set(self._tasks) | set(self._suspended)
        return [
            GraphNode(**{**n.__dict__, "status": "Running"}) if n.id in busy else n
            for n in await load_graph(self.engine.db, self.id)
        ]

    async def _emit_schedule(self, s: Schedule) -> None:
        key = (tuple(s.order), tuple(sorted(s.reasons.items())))
        if key == self._last_schedule:
            return
        self._last_schedule = key
        draft = EventDraft(
            type="schedule.updated",
            actor="orchestrator",
            data={"order": s.order, "reasons": s.reasons, "slots": s.slots},
        )
        await append_and_project(self.engine.db, self.id, [draft], self.engine.bus)

    async def _wait_any(self) -> None:
        wake = asyncio.create_task(self._wake.wait())
        try:
            await asyncio.wait({*self._tasks.values(), wake}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            wake.cancel()
        self._wake.clear()
        for nid in [n for n, t in self._tasks.items() if t.done()]:
            t = self._tasks.pop(nid)
            exc = None if t.cancelled() else t.exception()
            if isinstance(exc, ModelError | SearchError):
                await self._on_provider_error(nid, exc)  # from an orchestrator call after the node
            elif exc is not None:
                log.error("node task %s of %s failed", nid, self.id, exc_info=exc)

    async def _enter_paused(self, pause: tuple[str, str | None, str]) -> None:
        cause, detail, origin = pause
        gen = self._gen
        async with self.engine.db.tx() as tx:
            # A resume that committed while we waited for the writer ran its after_commit
            # (relaunch) before we got the lock: it bumped the generation; keep Running.
            if self._gen != gen:
                return
            row = await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [self.id])
            if row["state"] != "Running":
                return
            draft = EventDraft(
                type="investigation.state_changed",
                actor="user" if origin == "user" else "system",
                data={"from": "Running", "to": "Paused", "origin": origin, "cause": cause,
                      "detail": detail},
            )  # fmt: skip
            await append_and_project_in_tx(tx, self.id, [draft], self.engine.bus)

    # --- nodes -------------------------------------------------------------------------------

    def _start_node(self, nid: str) -> None:
        self._tasks[nid] = asyncio.create_task(self._node(nid), name=f"node:{nid}")

    async def _boundary(self) -> Signal:
        if self._stopping:
            return Signal.CANCEL
        if self._pause is None and await self._limit_reached():
            self._request_limit_pause()
        if self._pause is not None:
            return Signal.PAUSE
        return Signal.CONTINUE

    async def _limit_reached(self) -> bool:
        rows = await self.engine.db.read(
            "SELECT spent_usd, spending_limit_usd FROM investigations WHERE id = ?", [self.id]
        )
        return bool(rows) and rows[0]["spent_usd"] >= rows[0]["spending_limit_usd"]

    def _request_limit_pause(self) -> None:
        self.request_pause("spending_limit", "The spending limit was reached", "system")

    def _halting(self) -> bool:
        return self._stopping or self._pause is not None

    async def _node(self, nid: str) -> None:
        ctx = self._ctxs.get(nid)
        delays: list[float] | None = None  # the backoff of the current outage
        attempt = 0
        while True:
            try:
                if ctx is None:
                    ctx = self._ctxs[nid] = await node_context(
                        self._deps, self.id, nid, self._boundary
                    )
                await run_node(ctx)
                break
            except (ModelUnavailable, SearchUnavailable) as e:
                if delays is None:
                    delays = backoff_delays(self._retry_limit)
                if self._halting() or attempt >= len(delays):
                    self._suspended.append(nid)
                    if not self._halting():
                        await self._on_provider_error(nid, e)
                    return
                step = ctx.state.next_step[0] if ctx and ctx.state.next_step else "plan"
                await append_and_project(self.engine.db, self.id, [EventDraft(
                    type="node.activity", actor="node", node_id=nid,
                    data={"activity": "Retrying", "detail": str(e), "step": step,
                          "retry": {"n": attempt + 1, "m": len(delays)}},
                )], self.engine.bus)  # fmt: skip
                await self._deps.clock.sleep(delays[attempt])
                attempt += 1
                if self._halting():  # paused or stopped while waiting
                    self._suspended.append(nid)
                    return
            except (ModelError, SearchError) as e:
                self._suspended.append(nid)
                await self._on_provider_error(nid, e)
                return
            except Exception as e:
                log.exception("node %s of %s failed unexpectedly", nid, self.id)
                self._ctxs.pop(nid, None)
                await append_and_project(self.engine.db, self.id, [EventDraft(
                    type="node.failed", actor="node", node_id=nid,
                    data={"reason": f"internal error: {type(e).__name__}",
                          "auto_retry_used": False},
                )], self.engine.bus)  # fmt: skip
                try:
                    await orchestrator.on_node_failed(self._octx, nid)
                except Exception:
                    log.exception("retry decision for failed node %s of %s failed", nid, self.id)
                return
        if not ctx.state.done and ctx.node.status not in ("Completed", "Failed", "Rejected"):
            self._suspended.append(nid)  # returned at a boundary: continue it on resume
            return
        self._ctxs.pop(nid, None)
        status = (await self.engine.db.read("SELECT status FROM nodes WHERE id = ?", [nid]))[0][0]
        if status == "Completed":
            await orchestrator.on_node_returned(self._octx, nid)  # before anyone reads it
        elif status == "Waiting on children":
            rows = await self.engine.db.read(
                "SELECT id FROM nodes WHERE parent_id = ? AND status = 'Proposed'"
                " AND inclusion = 'Included' ORDER BY seq",
                [nid],
            )
            if rows:
                await orchestrator.review_proposals(self._octx, [r["id"] for r in rows])
        elif status == "Failed":
            await orchestrator.on_node_failed(self._octx, nid)

    async def _on_provider_error(self, nid: str, exc: Exception) -> None:
        """A provider error that is not retried (any more): pause the system way. The node
        keeps its context; its interrupted step runs again on resume."""
        log.warning("node %s: provider error (%s); pausing %s", nid, exc, self.id)
        self.request_pause(self._cause(exc), str(exc), "system")
        try:
            await self._mark_rejected_key(exc)
        except Exception:
            log.exception("could not mark the rejected key of %s", self.id)

    async def _mark_rejected_key(self, exc: Exception) -> None:
        if isinstance(exc, ModelRejected | SearchRejected) and exc.kind == "key":
            name = "model" if isinstance(exc, ModelRejected) else "search"
            await mark_key(self.engine.db, name, "rejected", str(exc))

    @staticmethod
    def _cause(exc: Exception) -> str:
        if isinstance(exc, ModelRejected | SearchRejected):
            cause = {"key": "key_rejected", "credit": "credit_exhausted"}.get(exc.kind)
            if cause:
                return cause
        return "model_unavailable" if isinstance(exc, ModelError) else "search_unavailable"
