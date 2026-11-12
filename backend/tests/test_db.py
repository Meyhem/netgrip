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
        assert [r["version"] for r in rows] == [1, 2]
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
