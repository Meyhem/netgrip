"""Rebuild state tables from the event log, and detect when they disagree with it."""

from netgrip.store import eventlog
from netgrip.store.db import Database, Tx
from netgrip.store.projections import ID_COLUMNS, STATE_TABLES, project


def _id_column(table: str) -> str:
    return ID_COLUMNS.get(table, "investigation_id")


async def _investigation_ids(tx: Tx) -> list[str]:
    rows = await tx.fetchall("SELECT DISTINCT investigation_id FROM events ORDER BY 1")
    return [r[0] for r in rows]


async def rebuild(db: Database, investigation_id: str | None = None) -> int:
    """Truncate state tables (for one investigation or all) and replay the log. Returns count."""
    replayed = 0
    async with db.tx() as tx:
        for table in reversed(STATE_TABLES):
            if investigation_id is None:
                await tx.execute(f"DELETE FROM {table}")
            else:
                await tx.execute(
                    f"DELETE FROM {table} WHERE {_id_column(table)} = ?", [investigation_id]
                )
        ids = [investigation_id] if investigation_id else await _investigation_ids(tx)
        for inv in ids:
            events = await eventlog.read_in_tx(tx, inv)
            await project(tx, events)
            replayed += len(events)
    return replayed


async def verify(db: Database) -> list[str]:
    """Ids whose state row is missing or whose `last_seq` differs from the log's last seq."""
    rows = await db.read(
        "SELECT e.investigation_id FROM"
        " (SELECT investigation_id, MAX(seq) AS seq FROM events GROUP BY investigation_id) e"
        " LEFT JOIN investigations i ON i.id = e.investigation_id"
        " WHERE i.id IS NULL OR i.last_seq != e.seq"
        " UNION"
        " SELECT i.id FROM investigations i"
        " WHERE NOT EXISTS (SELECT 1 FROM events e WHERE e.investigation_id = i.id)"
        " ORDER BY 1"
    )
    return [r[0] for r in rows]
