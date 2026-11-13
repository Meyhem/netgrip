"""One runtime per active investigation (D-04): in-process asyncio tasks that run up to
`effort.parallel` eligible nodes, check each result with the orchestrator, and conclude.

The loop: load the graph, schedule, start nodes into free slots, wait for one to return or a
request (pause, stop), repeat. When nothing runs and nothing is eligible the orchestrator
decides (O3); "conclude" hands over to synthesis.

Pause and stop act at step boundaries only: the node's `boundary` says pause or cancel, its
step in flight finishes and commits, and its `NodeContext` is kept, so resume continues the
node from its next step. A paused investigation enters Paused once nothing is in flight.

System pauses (N-05, B4):
- An outage (ModelUnavailable, SearchUnavailable) in a node is retried with delays 1, 2, 4 ...
  capped at 30 s, within the "retry before pausing" setting, shown as `Retrying` on the node.
  Then the investigation pauses (origin system) and the node is recorded back to Pending
  (`node.reset {reason: "outage"}`). It keeps its context: its interrupted step was not
  committed, so it runs again on resume.
- A rejected key or exhausted credit pauses at once; a rejected key is marked on the key. A
  refused request (`ModelRejected("request")`) is no pause: the node fails with that reason.
- The spending limit is checked by `call_model` before every model call (node steps and
  orchestrator calls alike) and before nodes are started: at or over the limit nothing is
  called; SpendingLimitReached becomes a `spending_limit` pause. So besides step boundaries,
  this pause also acts at a model-call boundary inside a step: a step that made its calls
  finishes and commits; one stopped before its call runs again on resume; a returned node's
  orchestrator work stays owed and runs on resume.
- Orchestrator calls get the same outage backoff as node steps (`retry_unavailable`).
- `start()` on an investigation whose nodes were reset by recovery (Task 8) just schedules
  them: a fresh context starts the node over.
- Return work that fails for a reason other than the provider (a bug) stays owed and is
  retried on the next resume or start; meanwhile the loop never concludes. With nothing else
  to run it ends, leaving the investigation Running (resume restarts it).
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from netgrip.adapters.model import ModelError, ModelRejected, ModelUnavailable
from netgrip.adapters.search import SearchError, SearchRejected, SearchUnavailable
from netgrip.boundary.events import EventDraft
from netgrip.engine import orchestrator
from netgrip.engine.agent import Deps, NodeContext, Signal, node_context, run_node
from netgrip.engine.brief import build_brief
from netgrip.engine.budget import SpendingLimitReached
from netgrip.engine.clock import Clock, SystemClock
from netgrip.engine.instructions import apply_queued
from netgrip.engine.orchestrator import OrchestratorContext
from netgrip.engine.scheduler import (
    GraphNode,
    Schedule,
    branch_ids,
    eligible,
    excluded,
    load_graph,
    schedule,
)
from netgrip.engine.synthesis import synthesise
from netgrip.evidence.service import EvidenceService
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


async def retry_unavailable[T](
    fn: Callable[[], Awaitable[T]],
    *,
    clock: Clock,
    limit: float,
    halted: asyncio.Event,
    on_retry: Callable[[int, int, Exception], Awaitable[None]] | None = None,
    progress: Callable[[], object] | None = None,
) -> T:
    """Run `fn`; on ModelUnavailable/SearchUnavailable wait (`backoff_delays(limit)`) and run
    it again. Raises the last outage when the delays run out or `halted` is set (a pause or
    stop also cuts a wait short). When `progress()` changed since the previous failure the
    work moved on, so the backoff starts over."""
    delays = backoff_delays(limit)
    attempt = 0
    last = progress() if progress else None
    while True:
        try:
            return await fn()
        except (ModelUnavailable, SearchUnavailable) as e:
            if progress is not None and (now := progress()) != last:
                last, attempt = now, 0
            if halted.is_set() or attempt >= len(delays):
                raise
            if on_retry is not None:
                await on_retry(attempt + 1, len(delays), e)
            sleep = asyncio.ensure_future(clock.sleep(delays[attempt]))
            halt = asyncio.ensure_future(halted.wait())
            try:
                await asyncio.wait({sleep, halt}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                sleep.cancel()
                halt.cancel()
            attempt += 1
            if halted.is_set():
                raise


def _held_by_user(graph: list[GraphNode], focus: str | None) -> bool:
    """Work is left that only the user's next move releases: a branch they paused, or nodes
    outside the one they run alone. The research is not finished, so it does not conclude."""
    by_id = {n.id: n for n in graph}
    if any(n.paused and not excluded(n, by_id) for n in graph if n.parent_id is not None):
        return True
    return bool(focus) and bool(eligible(graph)) and not eligible(graph, focus)


def _rejected_request(exc: Exception) -> bool:
    return isinstance(exc, ModelRejected) and exc.kind == "request"


class InvestigationRuntime:
    def __init__(self, engine: "Engine", investigation_id: str) -> None:
        self.engine = engine
        self.id = investigation_id
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._ctxs: dict[str, NodeContext] = {}  # kept across pause and stop
        self._suspended: list[str] = []  # returned at a boundary; continue these first
        self._pause: tuple[str, str | None, str] | None = None
        self._stopping = False
        self._finishing = False  # "Finish now": drain, then synthesise (S8)
        self._stepping: set[str] = (
            set()
        )  # nodes in the middle of run_node (a step may be in flight)
        self._wake = asyncio.Event()
        self._loop: asyncio.Task[None] | None = None
        self._last_schedule: tuple | None = None
        self._deps: Deps | None = None
        self._octx: OrchestratorContext | None = None
        self._gen = 0  # bumped by every (re)launch; a pause write from an older one is dropped
        self._retry_limit = 300.0
        self._halt = asyncio.Event()  # set by a pause or stop request: cuts backoff short
        self._owed: set[str] = set()  # returned nodes whose orchestrator work is still to do
        self._deferred: list[str] = []  # owed work that failed unexpectedly: retried on launch

    # --- control -----------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self._loop is not None and not self._loop.done()

    async def start(self) -> None:
        """Start (or continue) the loop. Creates a task only, so it is safe in after_commit."""
        self._launch()

    def _launch(self) -> None:
        self._gen += 1
        self._suspended += [n for n in self._deferred if n not in self._suspended]
        self._deferred.clear()
        self._stopping = False
        self._finishing = False
        self._pause = None
        self._halt.clear()
        if self.active:  # still draining a pause or stop: keep this loop going
            self._wake.set()
            return
        self._loop = asyncio.create_task(self._run(), name=f"runtime:{self.id}")

    def owe(self, node_ids: list[str]) -> None:
        """Return work a killed process left undone (recovery): run it first, steps skipped."""
        for nid in node_ids:
            if nid not in self._owed:
                self._owed.add(nid)
                self._suspended.append(nid)

    def resume(self) -> None:
        self._launch()

    def request_pause(self, cause: str, detail: str | None = None, origin: str = "user") -> None:
        """No new step starts; running steps finish; then Paused with this cause."""
        if self._pause is None:
            self._pause = (cause, detail, origin)
        self._halt.set()
        self._wake.set()

    def request_stop(self) -> None:
        """Like a pause, without a state change (the stop command already recorded Stopped)."""
        self._stopping = True
        self._halt.set()
        self._wake.set()

    def request_finish(self) -> None:
        """Like a pause, then the investigation finishes into a report instead (S8)."""
        self._finishing = True
        self._halt.set()
        self._wake.set()

    def wake(self) -> None:
        """Look at the graph again (the user changed something)."""
        self._wake.set()

    def in_flight(self, node_id: str | None) -> bool:
        """A step of the node may be in flight; its instructions wait for the boundary."""
        return node_id in self._stepping

    def busy(self, node_id: str) -> bool:
        """The node has a step in flight, a kept context or work still owed."""
        return (
            node_id in self._tasks or node_id in self._suspended
            or node_id in self._owed or node_id in self._deferred
        )  # fmt: skip

    @property
    def pausing(self) -> bool:
        return self.active and self._pause is not None

    async def stop(self, abandon: bool = False) -> None:
        """Let running steps finish (or, with `abandon`, cancel them: an uncommitted step is
        simply lost and runs again later), then end the loop."""
        self.request_stop()
        if abandon:
            tasks = list(self._tasks.values())
            for t in tasks:
                t.cancel()
            if self._loop is not None:
                self._loop.cancel()
            # Every cancelled node task has ended before we return: none can commit later.
            await asyncio.gather(*tasks, return_exceptions=True)
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
            pages=e.pages, evidence=evidence,
            clock=clock, bus=e.bus, prices=prices, limit_reached=self._limit_reached,
        )  # fmt: skip
        self._octx = OrchestratorContext(
            self.id, e.db, e.model_client, evidence, clock, e.bus, prices, self._limit_reached
        )
        # Return work a killed process owed (or one that died while Paused): from durable state.
        from netgrip.engine.recovery import owed_return_work

        self.owe(await owed_return_work(e.db, self.id))

    async def _apply_waiting_instructions(self) -> None:
        """Instructions queued while nothing could apply them (a restart, a pause, the
        spending limit) are applied before the loop starts."""
        try:
            await apply_queued(self.engine, self.id)
        except SpendingLimitReached:
            self._request_limit_pause()
        except (ModelError, SearchError) as e:
            self.request_pause(self._cause(e), str(e), "system")
            await self._mark_rejected_key(e)

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
            await self._apply_waiting_instructions()
            while True:
                # Read each time round: an effort change (or a changed setting) applies at once.
                parallel = await self._parallel()
                if self._finishing:
                    if not self._tasks:
                        await self._finish_now()
                        return
                elif self._stopping or self._pause is not None:
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
                        graph, focus = await self._graph(), await self._focus()
                        sched = schedule(graph, max(free, 0), focus)
                        await self._emit_schedule(sched)
                        for nid in sched.order[: max(free, 0)]:
                            self._start_node(nid)
                        if not self._tasks and self._deferred:
                            # Owed return work failed unexpectedly: never conclude past it.
                            log.error("runtime of %s: return work of %s owed; resume retries",
                                      self.id, self._deferred)  # fmt: skip
                            return
                        if not self._tasks and _held_by_user(graph, focus):
                            pass  # idle: the user paused a branch or runs only another one
                        elif not self._tasks:
                            try:
                                decision = await self._retrying(
                                    lambda: orchestrator.decide_next(self._octx)
                                )
                            except SpendingLimitReached:
                                self._request_limit_pause()
                                continue
                            if decision == "conclude":
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

    async def _finish_now(self) -> None:
        """Nothing is in flight any more: record the early end and write the report."""
        from netgrip.engine.steering import finishing_events

        async with self.engine.db.tx() as tx:
            state = await self._state_in(tx)
            if state not in ("Running", "Paused", "Stopped"):
                return
            await append_and_project_in_tx(tx, self.id, finishing_events(state), self.engine.bus)
        await synthesise(self.engine, self.id)

    async def _state_in(self, tx) -> str:
        row = await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [self.id])
        return row["state"] if row else ""

    async def _focus(self) -> str | None:
        rows = await self.engine.db.read(
            "SELECT focus_node_id FROM investigations WHERE id = ?", [self.id]
        )
        return rows[0]["focus_node_id"] if rows else None

    async def _graph(self) -> list[GraphNode]:
        busy = set(self._tasks) | set(self._suspended) | set(self._deferred)
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
        if self._stopping or self._finishing:
            return Signal.CANCEL
        if self._pause is not None:
            return Signal.PAUSE
        return Signal.CONTINUE

    async def _node_boundary(self, nid: str) -> Signal:
        """Before every step of node `nid`: the investigation's own signals, then what the
        user did to this node (paused, ignored, or a focus elsewhere)."""
        signal = await self._boundary()
        if signal == Signal.CONTINUE:
            # Instructions given to this node take effect now, before its next step (E4).
            await apply_queued(self.engine, self.id, nid)
            await self._refresh_brief(nid)
        if signal != Signal.CONTINUE:
            return signal
        graph = await load_graph(self.engine.db, self.id)
        by_id = {n.id: n for n in graph}
        node = by_id.get(nid)
        if node is None or node.paused or excluded(node, by_id):
            return Signal.PAUSE
        focus = await self._focus()
        if focus and nid not in branch_ids(graph, focus):
            return Signal.PAUSE
        return Signal.CONTINUE

    async def _refresh_brief(self, nid: str) -> None:
        """A node sees the instructions of itself and its ancestors from its next step: the
        brief is rebuilt when one was applied since it was built."""
        ctx = self._ctxs.get(nid)
        if ctx is None:
            return
        ids, cur = [], nid
        while cur:
            ids.append(cur)
            rows = await self.engine.db.read("SELECT parent_id FROM nodes WHERE id = ?", [cur])
            cur = rows[0]["parent_id"] if rows else None
        marks = ",".join("?" * len(ids))
        count = (await self.engine.db.read(
            f"SELECT COUNT(*) AS n FROM instructions WHERE state = 'applied' AND undone = 0"
            f" AND node_id IN ({marks})", ids))[0]["n"]  # fmt: skip
        if ctx.state.instructions_seen is None:
            ctx.state.instructions_seen = count
        elif count != ctx.state.instructions_seen:
            ctx.state.instructions_seen = count
            ctx.brief = await build_brief(self.engine.db, nid, self._deps.evidence)

    async def _apply_after_run(self, nid: str) -> None:
        """The node's loop returned (it may have completed before another boundary): apply
        what was queued for it now, so it is never left waiting."""
        if self._stopping or self._finishing or self._pause is not None:
            return
        try:
            await apply_queued(self.engine, self.id, nid)
        except SpendingLimitReached:
            self._request_limit_pause()
        except (ModelError, SearchError) as e:
            await self._on_provider_error(nid, e)
        except Exception:
            log.exception("applying the instructions of node %s of %s failed", nid, self.id)

    async def _returned_at_boundary(self, nid: str) -> None:
        """The node's loop returned before it finished. If the user took it out (ignore,
        focus elsewhere) it goes back to Pending and the scheduler decides about it; a branch
        pause leaves it Paused. Otherwise (pause, stop, limit) it is continued on resume."""
        graph = await load_graph(self.engine.db, self.id)
        by_id = {n.id: n for n in graph}
        node = by_id.get(nid)
        if node is None or node.status == "Paused":
            return
        focus = await self._focus()
        reason = (
            "ignored" if excluded(node, by_id)
            else "focus" if focus and nid not in branch_ids(graph, focus) else None
        )  # fmt: skip
        if reason is None:
            self._suspended.append(nid)
            return
        if node.status == "Running":
            await append_and_project(self.engine.db, self.id, [EventDraft(
                type="node.reset", actor="system", node_id=nid, data={"reason": reason},
            )], self.engine.bus)  # fmt: skip

    async def _limit_reached(self) -> bool:
        rows = await self.engine.db.read(
            "SELECT spent_usd, spending_limit_usd FROM investigations WHERE id = ?", [self.id]
        )
        return bool(rows) and rows[0]["spent_usd"] >= rows[0]["spending_limit_usd"]

    def _request_limit_pause(self) -> None:
        self.request_pause("spending_limit", "The spending limit was reached", "system")

    async def _node(self, nid: str) -> None:
        if nid not in self._owed:
            self._stepping.add(nid)
            try:
                returned = await self._steps(nid)
            finally:
                self._stepping.discard(nid)
            await self._apply_after_run(nid)
            if not returned:
                return
        await self._return_work(nid)

    async def _steps(self, nid: str) -> bool:
        """Run the node's steps. True when it returned (completed, failed or waits on
        children) and its return work is now owed; False when it was suspended."""
        ctx = self._ctxs.get(nid)
        try:
            if ctx is None:
                ctx = self._ctxs[nid] = await node_context(
                    self._deps, self.id, nid, lambda: self._node_boundary(nid)
                )
            c = ctx

            async def on_retry(n: int, m: int, exc: Exception) -> None:
                step = c.state.next_step[0] if c.state.next_step else "plan"
                await append_and_project(self.engine.db, self.id, [EventDraft(
                    type="node.activity", actor="node", node_id=nid,
                    data={"activity": "Retrying", "detail": str(exc), "step": step,
                          "retry": {"n": n, "m": m}},
                )], self.engine.bus)  # fmt: skip

            await self._retrying(lambda: run_node(c), on_retry, progress=lambda: c.state.steps)
        except SpendingLimitReached:
            self._suspended.append(nid)
            self._request_limit_pause()
            return False
        except (ModelError, SearchError) as e:
            if _rejected_request(e):
                # Not an outage and not the key: this request will be refused again as it is.
                # The node fails with the provider's reason; its failure handling is owed.
                log.warning("node %s of %s: the model refused the request (%s)", nid, self.id, e)
                self._ctxs.pop(nid, None)
                await self._fail(nid, f"The model refused the request: {e}")
                self._owed.add(nid)
                return True
            self._suspended.append(nid)
            await self._on_provider_error(nid, e)
            await self._reset_interrupted(nid)
            return False
        except Exception as e:
            log.exception("node %s of %s failed unexpectedly", nid, self.id)
            self._ctxs.pop(nid, None)
            await self._fail(nid, f"internal error: {type(e).__name__}")
            self._owed.add(nid)  # the retry decision is return work, with its error handling
            return True
        if not ctx.state.done and ctx.node.status not in ("Completed", "Failed", "Rejected"):
            await self._returned_at_boundary(nid)  # continued later, from its kept context
            return False
        self._ctxs.pop(nid, None)
        self._owed.add(nid)
        return True

    async def _fail(self, nid: str, reason: str) -> None:
        await append_and_project(self.engine.db, self.id, [EventDraft(
            type="node.failed", actor="node", node_id=nid,
            data={"reason": reason, "auto_retry_used": False},
        )], self.engine.bus)  # fmt: skip

    async def _return_work(self, nid: str) -> None:
        """The orchestrator's work on a returned node. It stays owed (and runs on resume) when
        the spending limit or a provider error stops it."""
        try:
            await self._retrying(lambda: self._after_return(nid))
        except SpendingLimitReached:
            self._suspended.append(nid)
            self._request_limit_pause()
            return
        except (ModelError, SearchError) as e:
            self._suspended.append(nid)
            await self._on_provider_error(nid, e)
            return
        except Exception:
            # Not the provider: retrying at once would likely fail the same way. It stays
            # owed and runs again on the next resume or start (recovery owes it after a kill).
            log.exception("return work of node %s of %s failed", nid, self.id)
            self._deferred.append(nid)
            return
        self._owed.discard(nid)

    async def _after_return(self, nid: str) -> None:
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

    async def _retrying[T](
        self,
        fn: Callable[[], Awaitable[T]],
        on_retry: Callable[[int, int, Exception], Awaitable[None]] | None = None,
        progress: Callable[[], object] | None = None,
    ) -> T:
        return await retry_unavailable(
            fn, clock=self._deps.clock, limit=self._retry_limit, halted=self._halt,
            on_retry=on_retry, progress=progress,
        )  # fmt: skip

    async def _reset_interrupted(self, nid: str) -> None:
        """The node's step was interrupted by the provider: back to Pending (reason outage).
        Its context is kept, so resume continues the uncommitted step."""
        try:
            await append_and_project(self.engine.db, self.id, [EventDraft(
                type="node.reset", actor="system", node_id=nid, data={"reason": "outage"},
            )], self.engine.bus)  # fmt: skip
        except Exception:
            log.exception("could not reset interrupted node %s of %s", nid, self.id)

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
        """The pause cause of a provider error. A model request refusal is not a pause: a node
        fails with it (`_steps`) and an orchestrator call falls back (`orchestrator._ask`)."""
        if isinstance(exc, ModelRejected | SearchRejected):
            cause = {"key": "key_rejected", "credit": "credit_exhausted"}.get(exc.kind)
            if cause:
                return cause
        return "model_unavailable" if isinstance(exc, ModelError) else "search_unavailable"
