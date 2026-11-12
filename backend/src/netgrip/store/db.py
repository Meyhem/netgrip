"""SQLite access: one writer connection behind a lock, one reader connection (WAL)."""

import asyncio
import re
import sqlite3
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import aiosqlite

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

Row = sqlite3.Row
AfterCommit = Callable[[], Awaitable[None] | None]


class Tx:
    """An open write transaction. Use only inside `Database.tx()`."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn
        self._after_commit: list[AfterCommit] = []

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        cur = await self._conn.execute(sql, tuple(params))
        return cur.rowcount

    async def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> None:
        await self._conn.executemany(sql, [tuple(r) for r in rows])

    async def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[Row]:
        cur = await self._conn.execute(sql, tuple(params))
        return list(await cur.fetchall())

    async def fetchone(self, sql: str, params: Iterable[Any] = ()) -> Row | None:
        cur = await self._conn.execute(sql, tuple(params))
        return await cur.fetchone()

    def after_commit(self, fn: AfterCommit) -> None:
        """Run `fn` once the transaction has committed (never on rollback)."""
        self._after_commit.append(fn)


class Database:
    def __init__(self, path: Path, writer: aiosqlite.Connection, reader: aiosqlite.Connection):
        self.path = path
        self._writer = writer
        self._reader = reader
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[Tx]:
        async with self._lock:
            await self._writer.execute("BEGIN IMMEDIATE")
            tx = Tx(self._writer)
            try:
                yield tx
            except BaseException:
                await self._writer.execute("ROLLBACK")
                raise
            await self._writer.execute("COMMIT")
        for fn in tx._after_commit:
            result = fn()
            if result is not None:
                await result

    async def read(self, sql: str, params: Iterable[Any] = ()) -> list[Row]:
        cur = await self._reader.execute(sql, tuple(params))
        try:
            return list(await cur.fetchall())
        finally:
            await cur.close()

    async def close(self) -> None:
        await self._reader.close()
        await self._writer.close()


async def _connect(path: Path) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    await conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def _migrations() -> list[tuple[int, str]]:
    found = []
    for f in sorted(MIGRATIONS_DIR.iterdir()):
        m = _MIGRATION_NAME.match(f.name)
        if m:
            found.append((int(m.group(1)), f.read_text()))
    return found


async def _migrate(conn: aiosqlite.Connection) -> None:
    await conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
    cur = await conn.execute("SELECT COALESCE(MAX(version), 0) FROM schema_version")
    current = (await cur.fetchone())[0]
    for version, sql in _migrations():
        if version <= current:
            continue
        try:
            await conn.executescript(
                f"BEGIN IMMEDIATE;\n{sql}\n;"
                f"INSERT INTO schema_version(version) VALUES ({version});\nCOMMIT;"
            )
        except Exception:
            if conn.in_transaction:
                await conn.execute("ROLLBACK")
            raise


async def open_db(path: Path) -> Database:
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = await _connect(path)
    await writer.execute("PRAGMA journal_mode = WAL")
    await writer.execute("PRAGMA synchronous = NORMAL")
    await _migrate(writer)
    reader = await _connect(path)
    return Database(path, writer, reader)
