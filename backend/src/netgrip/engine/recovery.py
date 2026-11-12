"""Recovery after a restart: resume the planning work a killed process left undone (R4).

Nothing is emitted here. The jobs it queues are the ones the command handlers queue, and they
re-check their state inside their own commit transaction, so a job that raced a duplicate
cannot apply an instruction or a draft twice."""

import logging
from typing import TYPE_CHECKING

from netgrip.engine.planner import draft_plan, replan

if TYPE_CHECKING:
    from netgrip.engine.engine import Engine

log = logging.getLogger(__name__)


async def recover_planning(engine: "Engine") -> None:
    """For every investigation in Planning: draft again if the plan never arrived (no version
    and no `plan.failed`), then re-queue each still-queued instruction in the order queued."""
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
