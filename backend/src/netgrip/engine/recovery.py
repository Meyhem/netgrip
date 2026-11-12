"""Recovery after a restart (R4, 6.2): rebuild state that disagrees with its log, resume the
planning work a killed process left undone, and continue research.

Research: for each Running investigation, nodes left Running go back to Pending
(`node.reset {reason: "recovery"}`) and run again; their steps are idempotent (extraction
cache, page dedup, claim dedup), so nothing paid for is repeated and no claim is duplicated.
Completed nodes are never re-run. Return work the killed process owed (the relevance gate of a
Completed node, the review of a waiting parent's proposals) is found from durable state and
done first. Paused and Stopped stay as they are; Synthesising restarts synthesis.

Planning: nothing is emitted. The jobs it queues are the ones the command handlers queue, and they
re-check their state inside their own commit transaction, so a job that raced a duplicate
cannot apply an instruction or a draft twice."""

import logging
from typing import TYPE_CHECKING

from netgrip.boundary.events import EventDraft
from netgrip.engine.planner import draft_plan, replan
from netgrip.engine.synthesis import synthesise
from netgrip.store.projections import append_and_project_in_tx
from netgrip.store.rebuild import rebuild, verify

if TYPE_CHECKING:
    from netgrip.engine.engine import Engine

log = logging.getLogger(__name__)


async def recover(engine: "Engine") -> None:
    """Called by `Engine.start`."""
    for inv in await verify(engine.db):
        log.warning("state of investigation %s disagrees with its log; rebuilding", inv)
        await rebuild(engine.db, inv)
    await recover_planning(engine)
    await recover_research(engine)


async def recover_research(engine: "Engine") -> None:
    rows = await engine.db.read(
        "SELECT id, state FROM investigations WHERE state IN ('Running', 'Synthesising')"
        " ORDER BY created_at, id"
    )
    for row in rows:
        inv = row["id"]
        if row["state"] == "Synthesising":
            log.info("restarting the synthesis of %s", inv)
            await synthesise(engine, inv)
            continue
        reset = await _reset_running(engine, inv)
        owed = await _owed_return_work(engine, inv)
        log.info("recovering %s: reset %s, return work owed for %s", inv, reset, owed)
        rt = engine.start_runtime(inv)
        if rt is not None:
            rt.owe(owed)  # before the loop's first turn (the launch only created its task)


async def _reset_running(engine: "Engine", inv: str) -> list[str]:
    """Running nodes back to Pending; Waiting on children stays (6.2)."""
    async with engine.db.tx() as tx:
        if (await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [inv]))[
            "state"
        ] != "Running":
            return []
        rows = await tx.fetchall(
            "SELECT id FROM nodes WHERE investigation_id = ? AND status = 'Running' ORDER BY seq",
            [inv],
        )
        ids = [r["id"] for r in rows]
        drafts = [
            EventDraft(type="node.reset", actor="system", node_id=nid, data={"reason": "recovery"})
            for nid in ids
        ]
        drafts.append(
            EventDraft(type="system.recovered", actor="system", data={"reset_node_ids": ids})
        )
        await append_and_project_in_tx(tx, inv, drafts, engine.bus)
    return ids


async def _owed_return_work(engine: "Engine", inv: str) -> list[str]:
    """Returned nodes whose orchestrator work never committed: a Completed node with no
    relevance decision, and a waiting parent with proposals still unreviewed."""
    rows = await engine.db.read(
        "SELECT id FROM nodes n WHERE investigation_id = ? AND ("
        " (status = 'Completed' AND relevance_checked = 0)"
        " OR (status = 'Waiting on children' AND EXISTS (SELECT 1 FROM nodes c"
        "  WHERE c.parent_id = n.id AND c.status = 'Proposed' AND c.inclusion = 'Included')))"
        " ORDER BY seq",
        [inv],
    )
    return [r["id"] for r in rows]


async def recover_planning(engine: "Engine") -> None:
    """For every investigation in Planning: draft again if the plan never arrived (no version
    and no `plan.failed` since the last `plan.draft_requested`, which clears it), then re-queue
    each still-queued instruction in the order queued."""
    if engine.model_client is None:
        return
    rows = await engine.db.read(
        "SELECT id, plan_failed_reason,"
        " (SELECT COUNT(*) FROM plan_versions WHERE investigation_id = i.id) AS versions"
        " FROM investigations i WHERE state = 'Planning' ORDER BY created_at, id"
    )
    for row in rows:
        inv = row["id"]
        if row["versions"] == 0 and row["plan_failed_reason"] is None:
            log.info("resuming the draft of %s", inv)
            engine.planning.enqueue(inv, _draft(engine, inv), "draft")
        queued = await engine.db.read(
            "SELECT id FROM instructions WHERE investigation_id = ? AND state = 'queued'"
            " ORDER BY queued_seq",
            [inv],
        )
        for q in queued:
            log.info("resuming the re-plan of %s for instruction %s", inv, q["id"])
            engine.planning.enqueue(inv, _replan(engine, inv, q["id"]), "replan")


def _draft(engine: "Engine", inv: str):
    return lambda: draft_plan(engine, inv, None)


def _replan(engine: "Engine", inv: str, instruction_id: str):
    return lambda: replan(engine, inv, instruction_id, None)
