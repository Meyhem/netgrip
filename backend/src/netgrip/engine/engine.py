"""The engine boundary: commands in (`submit`), events out (`subscribe`). Nothing else crosses."""

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from uuid import UUID

from netgrip.boundary.bus import Ephemeral, EventBus
from netgrip.boundary.commands import Command, CommandAck, CommandRejected
from netgrip.boundary.events import Event, EventDraft, utc_now_iso
from netgrip.config import Config
from netgrip.store import eventlog
from netgrip.store.db import Database, Tx
from netgrip.store.projections import ID_COLUMNS, STATE_TABLES, append_and_project_in_tx
from netgrip.store.rebuild import rebuild, verify
from netgrip.store.settings import get_settings, resolve_investigation_settings

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
    def __init__(self, db: Database, config: Config, bus: EventBus) -> None:
        self.db = db
        self.config = config
        self.bus = bus

    async def start(self) -> None:
        mismatched = await verify(self.db)
        for inv in mismatched:
            log.warning("state of investigation %s disagrees with its log; rebuilding", inv)
            await rebuild(self.db, inv)

    async def stop(self) -> None:
        pass

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

    async def delete_investigation(self, id: str) -> None:
        async with self.db.tx() as tx:
            if await tx.fetchone("SELECT 1 FROM investigations WHERE id = ?", [id]) is None:
                raise CommandRejected("not_found", "No such investigation")
            for table in reversed(STATE_TABLES):
                await tx.execute(
                    f"DELETE FROM {table} WHERE {ID_COLUMNS.get(table, 'investigation_id')} = ?",
                    [id],
                )
            await tx.execute("DELETE FROM events WHERE investigation_id = ?", [id])
            await tx.execute("DELETE FROM commands WHERE investigation_id = ?", [id])
            tx.after_commit(lambda: self.bus.end(id))

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
