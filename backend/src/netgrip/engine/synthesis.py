"""Synthesis. In Phase 4 a placeholder: Running/Synthesising -> Completed with `report.created`
and no report body. Phase 8 replaces the body (it reads `synthesis_claims()`)."""

import uuid
from typing import TYPE_CHECKING

from netgrip.boundary.events import EventDraft
from netgrip.store.projections import append_and_project_in_tx

if TYPE_CHECKING:
    from netgrip.engine.engine import Engine


def _changed(frm: str, to: str) -> EventDraft:
    return EventDraft(
        type="investigation.state_changed",
        actor="orchestrator",
        data={"from": frm, "to": to, "origin": "orchestrator"},
    )


async def synthesise(engine: "Engine", investigation_id: str) -> None:
    async with engine.db.tx() as tx:
        row = await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [investigation_id])
        if row is None or row["state"] not in ("Running", "Synthesising"):
            return  # stopped or paused meanwhile: nothing to synthesise now
        if row["state"] == "Running":
            await append_and_project_in_tx(
                tx, investigation_id, [_changed("Running", "Synthesising")], engine.bus
            )
    async with engine.db.tx() as tx:
        row = await tx.fetchone(
            "SELECT state, cut_short_by FROM investigations WHERE id = ?", [investigation_id]
        )
        if row["state"] != "Synthesising":
            return
        report = EventDraft(
            type="report.created",
            actor="orchestrator",
            data={
                "report_id": str(uuid.uuid4()),
                "ended_early": False,  # only "finish now" ends early (Phase 6)
                "cut_short_by": row["cut_short_by"],
            },
        )
        await append_and_project_in_tx(
            tx, investigation_id, [report, _changed("Synthesising", "Completed")], engine.bus
        )
