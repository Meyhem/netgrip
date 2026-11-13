"""Append-only, per-investigation event log (D-06)."""

import json

from netgrip.boundary.events import Event, EventDraft, upcast, utc_now_iso, validate_data
from netgrip.store.db import Database, Row, Tx

_COLUMNS = "investigation_id, seq, type, v, at, actor, node_id, command_id, data"


async def last_seq(tx: Tx, investigation_id: str) -> int:
    row = await tx.fetchone(
        "SELECT COALESCE(MAX(seq), 0) FROM events WHERE investigation_id = ?", [investigation_id]
    )
    return row[0]


async def append(tx: Tx, investigation_id: str, drafts: list[EventDraft]) -> list[Event]:
    seq = await last_seq(tx, investigation_id)
    at = utc_now_iso()
    events = []
    for draft in drafts:
        v, data = validate_data(draft.type, draft.data)
        seq += 1
        events.append(
            Event(
                seq=seq,
                investigation_id=investigation_id,
                type=draft.type,
                v=v,
                at=at,
                actor=draft.actor,
                node_id=draft.node_id,
                command_id=draft.command_id,
                data=data,
            )
        )
    await tx.executemany(
        f"INSERT INTO events({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                e.investigation_id,
                e.seq,
                e.type,
                e.v,
                e.at,
                e.actor,
                e.node_id,
                e.command_id,
                json.dumps(e.data, ensure_ascii=False),
            )
            for e in events
        ],
    )
    return events


def row_to_event(row: Row) -> Event:
    v, data = upcast(row["type"], row["v"], json.loads(row["data"]))
    return Event(
        seq=row["seq"],
        investigation_id=row["investigation_id"],
        type=row["type"],
        v=v,
        at=row["at"],
        actor=row["actor"],
        node_id=row["node_id"],
        command_id=row["command_id"],
        data=data,
    )


_SELECT = f"SELECT {_COLUMNS} FROM events WHERE investigation_id = ? AND seq > ? ORDER BY seq"


async def read(
    db: Database,
    investigation_id: str,
    after: int = 0,
    limit: int | None = None,
    *,
    before: int | None = None,
    actors: list[str] | None = None,
    node_id: str | None = None,
    types: list[str] | None = None,
) -> list[Event]:
    """Events after `after`, oldest first, at most `limit`. With `before`, the newest `limit`
    events below it (paging backwards), still oldest first. Filters narrow by actor, node and
    type."""
    where = ["investigation_id = ?", "seq > ?"]
    params: list = [investigation_id, after]
    if before is not None:
        where.append("seq < ?")
        params.append(before)
    for column, values in (("actor", actors), ("type", types)):
        if values:
            where.append(f"{column} IN ({','.join('?' * len(values))})")
            params += values
    if node_id is not None:
        where.append("node_id = ?")
        params.append(node_id)
    newest_first = before is not None and limit is not None
    sql = f"SELECT {_COLUMNS} FROM events WHERE {' AND '.join(where)}"
    sql += " ORDER BY seq DESC" if newest_first else " ORDER BY seq"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    rows = await db.read(sql, params)
    if newest_first:
        rows.reverse()
    return [row_to_event(r) for r in rows]


async def read_in_tx(tx: Tx, investigation_id: str, after: int = 0) -> list[Event]:
    return [row_to_event(r) for r in await tx.fetchall(_SELECT, [investigation_id, after])]
