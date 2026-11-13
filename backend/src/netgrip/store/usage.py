"""Disk usage per investigation (D-21): its events, its state rows and every page version it
references. A shared page counts in full for each investigation that uses it, so the figures
can sum to more than the data directory holds. Cached per investigation and refreshed when its
`last_seq` changes."""

from pathlib import Path

from netgrip.store.db import Database
from netgrip.store.projections import ID_COLUMNS, STATE_TABLES

# Tables kept for an investigation that are not event projections (caches of paid work).
OTHER_TABLES = ["extractions", "reconciled_claims", "investigation_pages"]


async def _columns(db: Database, table: str) -> list[str]:
    return [r["name"] for r in await db.read(f"PRAGMA table_info({table})")]


async def row_bytes(db: Database, table: str, investigation_id: str) -> int:
    """The stored size of the table's rows for the investigation: the byte length of every
    column value."""
    where = ID_COLUMNS.get(table, "investigation_id")
    cols = await _columns(db, table)
    size = " + ".join(f"COALESCE(LENGTH(CAST({c} AS BLOB)), 0)" for c in cols)
    rows = await db.read(
        f"SELECT COALESCE(SUM({size}), 0) FROM {table} WHERE {where} = ?", [investigation_id]
    )
    return int(rows[0][0])


def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


class DiskUsage:
    def __init__(self, db: Database, data_dir: Path) -> None:
        self.db = db
        self.root = data_dir / "pages"
        self._cache: dict[str, tuple[int, int]] = {}  # id -> (last_seq, bytes)

    def forget(self, investigation_id: str) -> None:
        self._cache.pop(investigation_id, None)

    async def pages_bytes(self, investigation_id: str) -> int:
        """Page files it references, each content-addressed file once."""
        rows = await self.db.read(
            "SELECT DISTINCT v.raw_sha, v.text_sha FROM investigation_pages ip"
            " JOIN page_versions v ON v.id = ip.page_version_id WHERE ip.investigation_id = ?",
            [investigation_id],
        )
        files = {self.root / r["raw_sha"][:2] / r["raw_sha"] for r in rows}
        files |= {self.root / r["text_sha"][:2] / f"{r['text_sha']}.txt" for r in rows}
        return sum(_file_size(f) for f in files)

    async def rows(self, investigation_id: str) -> int:
        """Events and state rows, not pages."""
        total = await row_bytes(self.db, "events", investigation_id)
        for table in [*STATE_TABLES, *OTHER_TABLES]:
            total += await row_bytes(self.db, table, investigation_id)
        return total

    async def of(self, investigation_id: str) -> int:
        seq = await self.db.read(
            "SELECT last_seq FROM investigations WHERE id = ?", [investigation_id]
        )
        if not seq:
            return 0
        last = seq[0]["last_seq"]
        cached = self._cache.get(investigation_id)
        if cached and cached[0] == last:
            return cached[1]
        total = await self.rows(investigation_id) + await self.pages_bytes(investigation_id)
        self._cache[investigation_id] = (last, total)
        return total
