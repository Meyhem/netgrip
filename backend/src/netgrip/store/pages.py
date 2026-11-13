"""The shared page store (V8, V9, D-10): every page is fetched once and kept as versions.

Bodies live on disk at `pages/<sha[:2]>/<sha>` (raw bytes) and `<sha>.txt` (extracted text),
content-addressed so identical bodies are stored once. Page tables are not event projections.
"""

import asyncio
import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from netgrip.adapters.fetcher import FetchAttempt, Fetcher, OnAttempt
from netgrip.store.db import Database

REUSE_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class PageVersion:
    id: str
    url: str
    fetched_at: datetime
    raw_sha: str
    text_sha: str
    title: str | None
    published_at: str | None
    bytes: int


@dataclass(frozen=True)
class Unobtainable:
    url: str
    attempts: list[FetchAttempt]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _to_version(row) -> PageVersion:
    return PageVersion(
        id=row["id"],
        url=row["url"],
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        raw_sha=row["raw_sha"],
        text_sha=row["text_sha"],
        title=row["title"],
        published_at=row["published_at"],
        bytes=row["bytes"],
    )


class PageStore:
    def __init__(self, db: Database, data_dir: Path, now: Callable[[], datetime] = _utcnow) -> None:
        self.db = db
        self.root = data_dir / "pages"
        self.now = now
        self._locks: dict[str, asyncio.Lock] = {}

    def _path(self, sha: str, suffix: str = "") -> Path:
        return self.root / sha[:2] / f"{sha}{suffix}"

    def _write_once(self, sha: str, data: bytes, suffix: str = "") -> None:
        path = self._path(sha, suffix)
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)

    async def get_or_fetch(
        self,
        investigation_id: str,
        url: str,
        reuse: Literal["1d", "always_refetch"],
        fetcher: Fetcher,
        on_attempt: OnAttempt,
    ) -> PageVersion | Unobtainable:
        # One lock per URL: concurrent callers queue behind the first fetch and then find its
        # version already linked to their investigation or fresh enough to reuse.
        lock = self._locks.setdefault(url, asyncio.Lock())
        async with lock:
            rows = await self.db.read(
                "SELECT v.* FROM page_versions v JOIN investigation_pages ip "
                "ON ip.page_version_id = v.id WHERE ip.investigation_id = ? AND v.url = ? "
                "ORDER BY v.fetched_at DESC LIMIT 1",
                (investigation_id, url),
            )
            if rows:  # V8: once per investigation
                return _to_version(rows[0])
            if reuse == "1d":
                rows = await self.db.read(
                    "SELECT v.* FROM pages p JOIN page_versions v ON v.id = p.latest_version_id "
                    "WHERE p.url = ?",
                    (url,),
                )
                if rows:
                    version = _to_version(rows[0])
                    if self.now() - version.fetched_at < REUSE_WINDOW:  # V9
                        await self._link(investigation_id, version.id)
                        return version
            result = await fetcher.fetch(url, on_attempt=on_attempt)
            if result.status != "ok" or result.page is None:
                return Unobtainable(url, result.attempts)
            page = result.page
            text = page.text.encode("utf-8")
            raw_sha, text_sha = _sha(page.raw), _sha(text)
            self._write_once(raw_sha, page.raw)
            self._write_once(text_sha, text, ".txt")
            version = PageVersion(
                uuid.uuid4().hex, url, self.now(), raw_sha, text_sha,
                page.title, page.published_at, len(page.raw),
            )  # fmt: skip
            async with self.db.tx() as tx:
                await tx.execute(
                    "INSERT INTO page_versions(id, url, fetched_at, raw_sha, text_sha, title, "
                    "published_at, bytes) VALUES (?,?,?,?,?,?,?,?)",
                    (version.id, url, version.fetched_at.isoformat(), raw_sha, text_sha,
                     version.title, version.published_at, version.bytes),
                )  # fmt: skip
                await tx.execute(
                    "INSERT INTO pages(url, latest_version_id) VALUES (?, ?) "
                    "ON CONFLICT(url) DO UPDATE SET latest_version_id = excluded.latest_version_id",
                    (url, version.id),
                )
                await tx.execute(
                    "INSERT OR IGNORE INTO investigation_pages VALUES (?, ?)",
                    (investigation_id, version.id),
                )
            return version

    async def _link(self, investigation_id: str, version_id: str) -> None:
        async with self.db.tx() as tx:
            await tx.execute(
                "INSERT OR IGNORE INTO investigation_pages VALUES (?, ?)",
                (investigation_id, version_id),
            )

    async def read_text(self, page_version_id: str) -> str:
        rows = await self.db.read(
            "SELECT text_sha FROM page_versions WHERE id = ?", (page_version_id,)
        )
        if not rows:
            raise KeyError(page_version_id)
        return self._path(rows[0]["text_sha"], ".txt").read_text(encoding="utf-8")

    async def drop_unreferenced(self, tx) -> list[tuple[str, str]]:
        """In the caller's transaction: remove the page versions no `investigation_pages` row
        references and repoint `pages` at what remains. Returns the (raw, text) shas of the
        versions removed; `remove_files` deletes the files they no longer share."""
        gone = await tx.fetchall(
            "SELECT raw_sha, text_sha FROM page_versions WHERE id NOT IN"
            " (SELECT page_version_id FROM investigation_pages)"
        )
        await tx.execute(
            "DELETE FROM page_versions WHERE id NOT IN"
            " (SELECT page_version_id FROM investigation_pages)"
        )
        await tx.execute(
            "UPDATE pages SET latest_version_id = (SELECT v.id FROM page_versions v"
            " WHERE v.url = pages.url ORDER BY v.fetched_at DESC LIMIT 1)"
            " WHERE latest_version_id NOT IN (SELECT id FROM page_versions)"
        )
        await tx.execute("DELETE FROM pages WHERE latest_version_id IS NULL")
        return [(r["raw_sha"], r["text_sha"]) for r in gone]

    async def remove_files(self, shas: list[tuple[str, str]]) -> int:
        """Delete the files of removed versions that no remaining version uses; returns the
        bytes freed."""
        freed = 0
        for raw_sha, text_sha in dict.fromkeys(shas):
            for sha, suffix, column in ((raw_sha, "", "raw_sha"), (text_sha, ".txt", "text_sha")):
                used = await self.db.read(
                    f"SELECT 1 FROM page_versions WHERE {column} = ? LIMIT 1", [sha]
                )
                path = self._path(sha, suffix)
                if used or not path.exists():
                    continue
                freed += path.stat().st_size
                path.unlink(missing_ok=True)
                try:
                    path.parent.rmdir()  # the fan-out directory, once empty
                except OSError:
                    pass
        return freed
