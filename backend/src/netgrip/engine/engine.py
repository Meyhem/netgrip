"""The engine boundary: commands in (`submit`), events out (`subscribe`). Nothing else crosses."""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from netgrip.adapters.fetcher import Fetcher
from netgrip.adapters.model import ModelClient
from netgrip.adapters.search import Search
from netgrip.boundary.bus import Ephemeral, EventBus
from netgrip.boundary.commands import Command, CommandAck, CommandRejected
from netgrip.boundary.events import Event, EventDraft, utc_now_iso
from netgrip.config import Config
from netgrip.engine.budget import allocate_budget
from netgrip.engine.clock import Clock
from netgrip.engine.limiter import resize_limiters
from netgrip.engine.planner import draft_plan, replan
from netgrip.engine.planning_queue import PlanningQueue
from netgrip.engine.recovery import recover
from netgrip.engine.runtime import InvestigationRuntime
from netgrip.store import eventlog
from netgrip.store.db import Database, Tx
from netgrip.store.pages import PageStore
from netgrip.store.projections import ID_COLUMNS, STATE_TABLES, append_and_project_in_tx
from netgrip.store.settings import Effort, get_settings, resolve_investigation_settings
from netgrip.store.usage import DiskUsage

log = logging.getLogger(__name__)

# A handler checks the command against current state (raising CommandRejected if it is not
# allowed) and returns the events it causes. It runs inside the command's transaction.
Handler = Callable[["Engine", Tx, Command], Awaitable[list[EventDraft]]]

_handlers: dict[str, Handler] = {}


def handles(type: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        _handlers[type] = fn
        return fn

    return register


async def _record_command(tx: Tx, command_id: str, investigation_id: str, type: str) -> bool:
    """Insert the command id; False if it was already recorded."""
    inserted = await tx.execute(
        "INSERT OR IGNORE INTO commands(id, investigation_id, type, recorded_at)"
        " VALUES (?, ?, ?, ?)",
        [command_id, investigation_id, type, utc_now_iso()],
    )
    return inserted == 1


class Engine:
    def __init__(
        self,
        db: Database,
        config: Config,
        bus: EventBus,
        model_client: ModelClient | None = None,
        *,
        search: Search | None = None,
        fetcher: Fetcher | None = None,
        clock: Clock | None = None,
        pages: PageStore | None = None,
        web=None,
    ) -> None:
        self.db = db
        self.config = config
        self.bus = bus
        self.model_client = model_client
        self.search = search
        self.fetcher = fetcher
        self.web = web  # the real adapters' owner (Phase 7); None with fakes
        self.clock = clock
        # One page store for every runtime: its in-flight fetch sharing (V8) and per-site
        # politeness only work when concurrent investigations go through the same one.
        self.pages = pages or PageStore(db, config.data_dir)
        self.planning = PlanningQueue()
        self.usage = DiskUsage(db, config.data_dir)
        self.runtimes: dict[str, InvestigationRuntime] = {}
        self._background: set[asyncio.Task] = set()

    def apply_settings(self, settings) -> None:
        """Resize the live limiters and pools; no restart needed."""
        resize_limiters(settings.capacity)
        if self.web is not None:
            self.web.apply(settings.capacity, settings.politeness_seconds)

    async def start(self) -> None:
        if self.web is not None:
            await self.web.start()
        self.apply_settings(await get_settings(self.db))
        await recover(self)

    def background(self, coro, name: str) -> None:
        """Run startup work (recovery's synthesis) without holding up `start`."""
        task = asyncio.create_task(coro, name=name)
        self._background.add(task)
        task.add_done_callback(self._background_done)

    def _background_done(self, task: "asyncio.Task") -> None:
        self._background.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("background task %s failed", task.get_name(), exc_info=task.exception())

    async def stop(self) -> None:
        for t in list(self._background):
            t.cancel()
        await asyncio.gather(*self._background, return_exceptions=True)
        await self.planning.stop()
        for rt in list(self.runtimes.values()):
            await rt.stop(abandon=True)
        if self.web is not None:
            await self.web.stop()

    @property
    def can_research(self) -> bool:
        """Research needs the web adapters; without them (Phase 7 adds the real ones) an
        approved plan stays Running with no runtime."""
        return (
            self.model_client is not None and self.search is not None and self.fetcher is not None
        )

    def start_runtime(self, investigation_id: str) -> "InvestigationRuntime | None":
        """Start (or continue) the investigation's runtime. Not async: safe in after_commit."""
        if not self.can_research:
            log.warning("no web adapters configured; %s will not run", investigation_id)
            return None
        rt = self.runtimes.get(investigation_id)
        if rt is None:
            rt = self.runtimes[investigation_id] = InvestigationRuntime(self, investigation_id)
        rt.resume()
        return rt

    async def submit(self, cmd: Command) -> CommandAck:
        async with self.db.tx() as tx:
            exists = await tx.fetchone(
                "SELECT 1 FROM investigations WHERE id = ?", [cmd.investigation_id]
            )
            if exists is None:
                raise CommandRejected("not_found", "No such investigation")
            handler = _handlers.get(cmd.type)
            if handler is None:
                raise CommandRejected("unknown_command", f"Unknown command {cmd.type!r}")
            if not await _record_command(tx, str(cmd.id), cmd.investigation_id, cmd.type):
                return CommandAck(recorded=True, duplicate=True)
            drafts = await handler(self, tx, cmd)
            for d in drafts:
                d.command_id = d.command_id or str(cmd.id)
            await append_and_project_in_tx(tx, cmd.investigation_id, drafts, self.bus)
        return CommandAck(recorded=True, duplicate=False)

    async def create_investigation(self, id: UUID, prompt: str, settings: dict) -> CommandAck:
        """`settings` holds what the user chose; the rest comes from the global settings."""
        if not prompt.strip():
            raise CommandRejected("empty_prompt", "The prompt is empty")
        inv = str(id)
        settings = resolve_investigation_settings(await get_settings(self.db), settings)
        async with self.db.tx() as tx:
            if not await _record_command(tx, inv, inv, "create_investigation"):
                return CommandAck(recorded=True, duplicate=True)
            draft = EventDraft(
                type="investigation.created",
                actor="user",
                command_id=inv,
                data={"prompt": prompt, "settings": settings},
            )
            await append_and_project_in_tx(tx, inv, [draft], self.bus)
        return CommandAck(recorded=True, duplicate=False)

    async def delete_investigation(self, id: str) -> int:
        """Stop everything that could write for it and wait until it has ended, then remove
        its events, commands, state, evidence, report and page links in one transaction, then
        the page versions and files no other investigation uses. Returns the bytes freed.
        Nothing is pruned any other way (C-10)."""
        rt = self.runtimes.pop(id, None)
        if rt is not None:
            await rt.stop(abandon=True)
        await self.planning.cancel(id)
        await self._cancel_background(id)
        rows_bytes = await self.usage.rows(id)
        async with self.db.tx() as tx:
            if await tx.fetchone("SELECT 1 FROM investigations WHERE id = ?", [id]) is None:
                raise CommandRejected("not_found", "No such investigation")
            for table in reversed(STATE_TABLES):
                await tx.execute(
                    f"DELETE FROM {table} WHERE {ID_COLUMNS.get(table, 'investigation_id')} = ?",
                    [id],
                )
            for table in ("extractions", "reconciled_claims", "investigation_pages"):
                await tx.execute(f"DELETE FROM {table} WHERE investigation_id = ?", [id])
            await tx.execute("DELETE FROM events WHERE investigation_id = ?", [id])
            await tx.execute("DELETE FROM commands WHERE investigation_id = ?", [id])
            shas = await self.pages.drop_unreferenced(tx)
            tx.after_commit(lambda: self.bus.end(id))
        self.usage.forget(id)
        return rows_bytes + await self.pages.remove_files(shas)

    async def _cancel_background(self, id: str) -> None:
        """Synthesis and finishing run as background tasks named after the investigation."""
        mine = [t for t in self._background if t.get_name() in (f"finish:{id}", f"synthesis:{id}")]
        for t in mine:
            t.cancel()
        await asyncio.gather(*mine, return_exceptions=True)

    def publish_ephemeral(self, item: Ephemeral) -> None:
        self.bus.publish(item)

    async def subscribe(
        self, investigation_id: str, after_seq: int = 0
    ) -> AsyncIterator[Event | Ephemeral]:
        """Durable events after `after_seq` from the log, then live; no gap, no duplicate.

        An `after_seq` past the end of the log continues from the end.
        """
        sub = self.bus.subscribe(investigation_id)  # register before reading the log
        try:
            end = await self.db.read(
                "SELECT COALESCE(MAX(seq), 0) FROM events WHERE investigation_id = ?",
                [investigation_id],
            )
            last = min(after_seq, end[0][0])
            for event in await eventlog.read(self.db, investigation_id, after=last):
                last = event.seq
                yield event
            async for item in sub:
                if isinstance(item, Ephemeral):
                    yield item
                    continue
                if item.seq <= last:
                    continue
                if item.seq > last + 1:  # fill any gap from the log
                    for missed in await eventlog.read(
                        self.db, investigation_id, after=last, limit=item.seq - last - 1
                    ):
                        last = missed.seq
                        yield missed
                last = item.seq
                yield item
        finally:
            sub.close()


# --- Planning (Phase 3) ----------------------------------------------------------------------

ACTIVE_STATES = ("Planning", "Running", "Paused", "Synthesising")


async def _has_model_key(engine: Engine, tx: Tx) -> bool:
    """Fake mode counts the key as present (R3)."""
    if engine.config.fake:
        return engine.model_client is not None
    if engine.model_client is None:
        return False
    return await tx.fetchone("SELECT 1 FROM secrets WHERE name = 'model'") is not None


@handles("draft_plan")
async def _draft_plan(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Draft → Planning now, then plan.draft_requested; the draft itself runs on the planning
    queue after commit (R4).

    Also allowed after `plan.failed` (Planning, no plan version yet, nothing queued), so the
    user can ask again; then only plan.draft_requested is emitted, which clears the failure,
    so a restart during the re-draft resumes it (R16)."""
    inv = cmd.investigation_id
    row = await tx.fetchone(
        "SELECT state, plan_failed_reason,"
        " (SELECT COUNT(*) FROM plan_versions WHERE investigation_id = i.id) AS versions"
        " FROM investigations i WHERE id = ?",
        [inv],
    )
    redraft = (
        row["state"] == "Planning"
        and row["versions"] == 0
        and row["plan_failed_reason"] is not None
        and not engine.planning.busy(inv)
    )
    if row["state"] != "Draft" and not redraft:
        raise CommandRejected("wrong_state", "The plan can only be drafted from Draft")
    if not await _has_model_key(engine, tx):
        raise CommandRejected("no_model_key", "No model key is set")
    drafts: list[EventDraft] = []
    if not redraft:
        limit = (await get_settings(engine.db)).capacity.investigations
        placeholders = ",".join("?" * len(ACTIVE_STATES))
        active = await tx.fetchone(
            f"SELECT COUNT(*) FROM investigations WHERE state IN ({placeholders})",
            list(ACTIVE_STATES),
        )
        if active[0] >= limit:
            raise CommandRejected("parallel_limit", f"{limit} investigations are already active")
        drafts.append(
            EventDraft(
                type="investigation.state_changed",
                actor="user",
                data={"from": "Draft", "to": "Planning", "origin": "user"},
            )
        )
    drafts.append(EventDraft(type="plan.draft_requested", actor="user", data={}))
    command_id = str(cmd.id)
    tx.after_commit(
        lambda: engine.planning.enqueue(inv, lambda: draft_plan(engine, inv, command_id), "draft")
    )
    return drafts


async def _plan_under_review(engine: Engine, tx: Tx, inv: str, busy_code: str | None) -> dict:
    """The investigation in plan review: Planning with a plan (version >= 1), else 409
    wrong_state. With `busy_code`, also 409 `busy_code` while a planning job is queued or
    running."""
    row = await tx.fetchone(
        "SELECT state, settings,"
        " (SELECT COALESCE(MAX(version), 0) FROM plan_versions"
        "  WHERE investigation_id = i.id) AS version,"
        " (SELECT id FROM nodes WHERE investigation_id = i.id AND parent_id IS NULL"
        "  ORDER BY seq LIMIT 1) AS root_id"
        " FROM investigations i WHERE id = ?",
        [inv],
    )
    if row["state"] != "Planning" or row["version"] == 0:
        raise CommandRejected("wrong_state", "There is no plan under review")
    if busy_code and engine.planning.busy(inv):
        raise CommandRejected(busy_code, "The plan is being re-planned")
    return dict(row)


@handles("instruct_plan")
async def _instruct_plan(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Queue an instruction to the root (U6); the re-plan runs on the planning queue after
    commit (R4). Allowed while another re-plan runs: they apply in order, one version each."""
    inv = cmd.investigation_id
    plan = await _plan_under_review(engine, tx, inv, busy_code=None)
    text = str(cmd.payload.get("text") or "").strip()
    if not text:
        raise CommandRejected("empty_instruction", "The instruction is empty")
    if not await _has_model_key(engine, tx):
        raise CommandRejected("no_model_key", "No model key is set")
    instruction_id = str(uuid.uuid4())
    command_id = str(cmd.id)
    tx.after_commit(
        lambda: engine.planning.enqueue(
            inv, lambda: replan(engine, inv, instruction_id, command_id), "replan"
        )
    )
    return [
        EventDraft(
            type="instruction.queued",
            actor="user",
            node_id=plan["root_id"],
            data={"instruction_id": instruction_id, "text": text, "waiting_for": "replan"},
        )
    ]


@handles("undo_plan_instruction")
async def _undo_plan_instruction(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Undo the instruction behind the current version (R8): supersede what it proposed,
    restore what it superseded, and go back one version."""
    inv = cmd.investigation_id
    plan = await _plan_under_review(engine, tx, inv, busy_code="replanning")
    if plan["version"] <= 1:
        raise CommandRejected("nothing_to_undo", "No instruction is left to undo")
    current = await tx.fetchone(
        "SELECT instruction_id, diff FROM plan_versions WHERE investigation_id = ? AND version = ?",
        [inv, plan["version"]],
    )
    iid = current["instruction_id"]
    diff = json.loads(current["diff"])

    async def having(ids: list[str], inclusion: str) -> list[str]:
        if not ids:
            return []
        marks = ",".join("?" * len(ids))
        rows = await tx.fetchall(
            f"SELECT id FROM nodes WHERE id IN ({marks}) AND inclusion = ?", [*ids, inclusion]
        )
        found = {r["id"] for r in rows}
        return [i for i in ids if i in found]

    drafts = []
    for ids, inclusion in (
        (await having(diff["proposed"], "Included"), "Superseded"),
        (await having(diff["superseded"], "Superseded"), "Included"),
    ):
        if ids:
            drafts.append(
                EventDraft(
                    type="node.inclusion_changed",
                    actor="user",
                    data={
                        "node_ids": ids,
                        "inclusion": inclusion,
                        "by": "replan",
                        "instruction_id": iid,
                    },
                )
            )
    drafts.append(
        EventDraft(
            type="plan.reverted",
            actor="user",
            data={"to_version": plan["version"] - 1, "instruction_id": iid},
        )
    )
    return drafts


@handles("approve_plan")
async def _approve_plan(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Approve every Included planned node and R with its budget (O2), then Planning ->
    Running. Superseded and ignored nodes are not approved."""
    inv = cmd.investigation_id
    plan = await _plan_under_review(engine, tx, inv, busy_code="replanning")
    effort = Effort.model_validate(json.loads(plan["settings"])["effort_budget"])
    rows = await tx.fetchall(
        "SELECT id, depth FROM nodes WHERE investigation_id = ? AND inclusion = 'Included'"
        " AND status = 'Proposed' ORDER BY seq",
        [inv],
    )
    tx.after_commit(lambda: engine.start_runtime(inv) and None)
    return [
        *(
            EventDraft(
                type="node.approved",
                actor="orchestrator",
                node_id=r["id"],
                data={"budget": allocate_budget(effort, r["depth"]).as_dict()},
            )
            for r in rows
        ),
        EventDraft(
            type="investigation.state_changed",
            actor="user",
            data={"from": "Planning", "to": "Running", "origin": "user"},
        ),
    ]


# --- Running (Phase 4) -----------------------------------------------------------------------


async def _state_of(tx: Tx, inv: str) -> str:
    return (await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [inv]))["state"]


def _state_changed(frm: str, to: str, **extra: object) -> EventDraft:
    return EventDraft(
        type="investigation.state_changed",
        actor="user",
        data={"from": frm, "to": to, "origin": "user", **extra},
    )


@handles("pause")
async def _pause(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """No new step starts; running steps finish; then Paused (origin user). Without a live
    runtime nothing is in flight, so Paused is recorded at once."""
    inv = cmd.investigation_id
    rt = engine.runtimes.get(inv)
    if await _state_of(tx, inv) != "Running" or (rt is not None and rt.pausing):
        raise CommandRejected("wrong_state", "Only a running investigation can be paused")
    if rt is not None and rt.active:
        tx.after_commit(lambda: rt.request_pause("user", None, "user"))
        return []
    return [_state_changed("Running", "Paused", cause="user", detail=None)]


@handles("resume")
async def _resume(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Paused or Stopped -> Running; nodes stopped at a boundary continue from their next
    step. Refused with `limit_reached` while the spending limit is still reached (B4): the
    interface raises the limit first, then resumes."""
    inv = cmd.investigation_id
    current = await _state_of(tx, inv)
    spend = await tx.fetchone(
        "SELECT spent_usd, spending_limit_usd FROM investigations WHERE id = ?", [inv]
    )
    if current in ("Paused", "Stopped") and spend["spent_usd"] >= spend["spending_limit_usd"]:
        raise CommandRejected("limit_reached", "The spending limit is reached; raise it first")
    rt = engine.runtimes.get(inv)
    if current == "Running":
        # A pause still draining is cancelled; a runtime that ended on an internal error is
        # restarted. Neither changes the state.
        if (rt is not None and rt.pausing) or (
            engine.can_research and (rt is None or not rt.active)
        ):
            tx.after_commit(lambda: engine.start_runtime(inv) and None)
            return []
        raise CommandRejected("wrong_state", "The investigation is already running")
    if current not in ("Paused", "Stopped"):
        raise CommandRejected("wrong_state", "Only a paused or stopped investigation resumes")
    if current == "Paused" and await _paused_while_synthesising(tx, inv):
        from netgrip.engine.synthesis import synthesise

        tx.after_commit(lambda: engine.background(synthesise(engine, inv), f"synthesis:{inv}"))
        return [_state_changed("Paused", "Synthesising")]
    tx.after_commit(lambda: engine.start_runtime(inv) and None)
    return [_state_changed(current, "Running")]


async def _paused_while_synthesising(tx: Tx, inv: str) -> bool:
    """The pause came while the report was being written: resume writes it again."""
    row = await tx.fetchone(
        "SELECT json_extract(data, '$.from') AS frm FROM events WHERE investigation_id = ?"
        " AND type = 'investigation.state_changed' AND json_extract(data, '$.to') = 'Paused'"
        " ORDER BY seq DESC LIMIT 1",
        [inv],
    )
    return row is not None and row["frm"] == "Synthesising"


@handles("stop")
async def _stop(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Running or Paused -> Stopped. Everything is kept; steps in flight finish and commit;
    `resume` continues."""
    inv = cmd.investigation_id
    current = await _state_of(tx, inv)
    if current not in ("Running", "Paused"):
        raise CommandRejected("wrong_state", "Only a running or paused investigation stops")
    rt = engine.runtimes.get(inv)
    if rt is not None:
        tx.after_commit(rt.request_stop)
    return [_state_changed(current, "Stopped")]


@handles("raise_limit")
async def _raise_limit(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Set a new spending limit (`limit.changed`). It does not resume by itself."""
    inv = cmd.investigation_id
    value = cmd.payload.get("spending_limit_usd")
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise CommandRejected("invalid_limit", "The spending limit must be a positive amount")
    if await _state_of(tx, inv) in ("Draft", "Completed"):
        raise CommandRejected("wrong_state", "The limit can not be changed now")
    return [EventDraft(type="limit.changed", actor="user", data={"spending_limit_usd": value})]


from netgrip.engine import steering  # noqa: E402,F401  (registers the steering handlers)
