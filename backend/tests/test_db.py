import asyncio

import pytest

from netgrip.store.db import open_db


async def test_wal_enabled(tmp_path):
    db = await open_db(tmp_path / "n.sqlite")
    try:
        rows = await db.read("PRAGMA journal_mode")
        assert rows[0][0] == "wal"
    finally:
        await db.close()


async def test_migrations_run_once(tmp_path):
    path = tmp_path / "n.sqlite"
    for _ in range(2):
        db = await open_db(path)
        rows = await db.read("SELECT version FROM schema_version")
        assert [r["version"] for r in rows] == [1, 2, 3, 4, 5, 6, 7, 8]
        await db.close()


async def test_tx_rolls_back_on_error(tmp_path):
    db = await open_db(tmp_path / "n.sqlite")
    try:
        with pytest.raises(RuntimeError):
            async with db.tx() as tx:
                await tx.execute("INSERT INTO settings(key, value) VALUES ('a', '1')")
                raise RuntimeError("boom")
        assert await db.read("SELECT * FROM settings WHERE key = 'a'") == []
        async with db.tx() as tx:
            await tx.execute("INSERT INTO settings(key, value) VALUES ('a', '1')")
        assert len(await db.read("SELECT * FROM settings WHERE key = 'a'")) == 1
    finally:
        await db.close()


class GatedBegin:
    """Sends the next BEGIN IMMEDIATE of `db`'s writer to SQLite at once, but holds its answer
    until `release` is set: a cancel meanwhile arrives after the BEGIN took effect."""

    def __init__(self, db):
        self.db = db
        self.real = db._writer.execute
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        self.armed = True
        db._writer.execute = self.execute

    async def execute(self, sql, *args):
        if sql == "BEGIN IMMEDIATE" and self.armed:
            self.armed = False
            sent = asyncio.ensure_future(self.real(sql, *args))
            self.entered.set()
            await self.release.wait()
            return await sent
        return await self.real(sql, *args)


async def test_cancel_during_begin_leaves_the_writer_usable(tmp_path):
    db = await open_db(tmp_path / "n.sqlite")
    try:
        gate = GatedBegin(db)

        async def write():
            async with db.tx() as tx:
                await tx.execute("INSERT INTO settings(key, value) VALUES ('a', '1')")

        task = asyncio.create_task(write())
        await gate.entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        gate.release.set()  # BEGIN completes after the cancel arrived
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not db._writer.in_transaction
        assert not db._lock.locked()
        async with db.tx() as tx:
            await tx.execute("INSERT INTO settings(key, value) VALUES ('b', '1')")
        rows = await db.read("SELECT key FROM settings ORDER BY key")
        assert [r["key"] for r in rows] == ["b"]  # the cancelled write never happened
    finally:
        await db.close()


async def test_cancel_at_any_point_of_a_tx_never_wedges_the_writer(tmp_path):
    db = await open_db(tmp_path / "n.sqlite")
    try:
        for i in range(60):

            async def write(i=i):
                async with db.tx() as tx:
                    await tx.execute("INSERT INTO settings(key, value) VALUES (?, '1')", [f"k{i}"])

            task = asyncio.create_task(write())
            for _ in range(i % 6):
                await asyncio.sleep(0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            async with db.tx() as tx:  # raised "cannot start a transaction within a transaction"
                await tx.execute("SELECT 1")
    finally:
        await db.close()


async def test_cancel_during_commit_still_runs_after_commit(tmp_path):
    db = await open_db(tmp_path / "n.sqlite")
    try:
        real = db._writer.execute
        entered, release = asyncio.Event(), asyncio.Event()

        async def execute(sql, *args):
            if sql == "COMMIT":
                entered.set()
                await release.wait()
            return await real(sql, *args)

        db._writer.execute = execute
        ran = []

        async def write():
            async with db.tx() as tx:
                await tx.execute("INSERT INTO settings(key, value) VALUES ('a', '1')")
                tx.after_commit(lambda: ran.append(True))

        task = asyncio.create_task(write())
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
        db._writer.execute = real
        assert ran == [True]
        assert len(await db.read("SELECT * FROM settings WHERE key = 'a'")) == 1
        assert not db._writer.in_transaction
    finally:
        await db.close()
