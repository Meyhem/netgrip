"""The per-investigation planning queue (R4): one worker per investigation runs its planning
jobs (the initial draft, re-plans) one at a time, in the order they were queued, outside any
command transaction. A worker ends when its queue is empty."""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)

Job = Callable[[], Awaitable[None]]


@dataclass
class _Queued:
    kind: str
    run: Job


class PlanningQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, deque[_Queued]] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._current: dict[str, str] = {}

    def enqueue(self, investigation_id: str, job: Job, kind: str = "draft") -> None:
        """Queue `job`; start the investigation's worker if it is not running. Not async, so
        it can be called from `Tx.after_commit`."""
        self._jobs.setdefault(investigation_id, deque()).append(_Queued(kind, job))
        if investigation_id not in self._workers:
            self._workers[investigation_id] = asyncio.create_task(
                self._work(investigation_id), name=f"planning:{investigation_id}"
            )

    def busy(self, investigation_id: str) -> bool:
        """A job is running or queued for the investigation."""
        return investigation_id in self._workers

    def running(self, investigation_id: str) -> str | None:
        """The kind of the job running now, if any."""
        return self._current.get(investigation_id)

    def queued(self, investigation_id: str) -> list[str]:
        """Kinds of the jobs waiting behind the running one, in order."""
        return [q.kind for q in self._jobs.get(investigation_id, ())]

    async def idle(self, investigation_id: str) -> None:
        """Wait until the investigation has no job running or queued."""
        while (task := self._workers.get(investigation_id)) is not None:
            await asyncio.wait({task})

    async def cancel(self, investigation_id: str) -> None:
        """Drop the investigation's queued jobs and cancel the running one; returns when its
        worker has ended, so nothing of it writes afterwards."""
        if (queued := self._jobs.get(investigation_id)) is not None:
            queued.clear()
        task = self._workers.get(investigation_id)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def stop(self) -> None:
        """Cancel every worker and wait for them to end. Queued jobs are dropped."""
        tasks = list(self._workers.values())
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._workers.clear()
        self._jobs.clear()
        self._current.clear()

    async def _work(self, investigation_id: str) -> None:
        jobs = self._jobs[investigation_id]
        try:
            while jobs:
                job = jobs.popleft()
                self._current[investigation_id] = job.kind
                try:
                    await job.run()
                except Exception:
                    log.exception("planning job %s for %s failed", job.kind, investigation_id)
                finally:
                    self._current.pop(investigation_id, None)
        finally:
            # No await between the empty check and these, so enqueue never misses a worker.
            self._workers.pop(investigation_id, None)
            if not jobs:
                self._jobs.pop(investigation_id, None)
