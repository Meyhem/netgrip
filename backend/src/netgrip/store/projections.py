"""Projectors keep the state tables in step with the event log, in the same transaction (D-06)."""

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Protocol

from netgrip.boundary.events import Event, EventDraft
from netgrip.store import eventlog
from netgrip.store.db import Database, Tx

Projector = Callable[[Tx, Event], Awaitable[None]]

_projectors: dict[str, list[Projector]] = defaultdict(list)

# Tables a rebuild truncates and refills from the log. Later migrations append to this list.
STATE_TABLES: list[str] = ["investigations"]

# Column holding the investigation id, for tables where it is not `investigation_id`.
ID_COLUMNS: dict[str, str] = {"investigations": "id"}


class Publisher(Protocol):
    def publish(self, item: Event) -> None: ...


def projector(type: str) -> Callable[[Projector], Projector]:
    def register(fn: Projector) -> Projector:
        _projectors[type].append(fn)
        return fn

    return register


async def project(tx: Tx, events: list[Event]) -> None:
    """Run every projector for `events`, then stamp the investigation row."""
    for event in events:
        for fn in _projectors.get(event.type, ()):
            await fn(tx, event)
    if events:
        last = events[-1]
        await tx.execute(
            "UPDATE investigations SET last_seq = ?, last_activity_at = ? WHERE id = ?",
            [last.seq, last.at, last.investigation_id],
        )


async def append_and_project_in_tx(
    tx: Tx, investigation_id: str, drafts: list[EventDraft], bus: Publisher | None = None
) -> list[Event]:
    events = await eventlog.append(tx, investigation_id, drafts)
    await project(tx, events)
    if bus is not None:

        def _publish() -> None:
            for e in events:
                bus.publish(e)

        tx.after_commit(_publish)
    return events


async def append_and_project(
    db: Database, investigation_id: str, drafts: list[EventDraft], bus: Publisher | None = None
) -> list[Event]:
    async with db.tx() as tx:
        return await append_and_project_in_tx(tx, investigation_id, drafts, bus)


# --- Phase 1 projectors ----------------------------------------------------------------------


@projector("investigation.created")
async def _created(tx: Tx, event: Event) -> None:
    settings = event.data["settings"]
    await tx.execute(
        "INSERT INTO investigations(id, prompt, state, settings, spending_limit_usd,"
        " created_at, last_activity_at) VALUES (?, ?, 'Draft', ?, ?, ?, ?)",
        [
            event.investigation_id,
            event.data["prompt"],
            json.dumps(settings, ensure_ascii=False),
            float(settings.get("spending_limit_usd", 5.0)),
            event.at,
            event.at,
        ],
    )


@projector("investigation.state_changed")
async def _state_changed(tx: Tx, event: Event) -> None:
    paused = event.data["to"] == "Paused"
    await tx.execute(
        "UPDATE investigations SET state = ?, pause_cause = ?, pause_detail = ? WHERE id = ?",
        [
            event.data["to"],
            event.data.get("cause") if paused else None,
            event.data.get("detail") if paused else None,
            event.investigation_id,
        ],
    )
