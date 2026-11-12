"""Investigation queries: list rows, snapshot, events; create and delete."""

import json
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from netgrip.api.deps import get_db, get_engine
from netgrip.boundary.commands import CommandAck
from netgrip.engine.engine import Engine
from netgrip.store import eventlog
from netgrip.store.db import Database, Row

router = APIRouter(prefix="/api/investigations")


class CreateInvestigation(BaseModel):
    id: UUID
    prompt: str
    settings: dict[str, Any] = Field(default_factory=dict)


def list_row(r: Row) -> dict[str, Any]:
    settings = json.loads(r["settings"])
    return {
        "id": r["id"],
        "prompt": r["prompt"],
        "state": r["state"],
        "pause_cause": r["pause_cause"],
        "pause_detail": r["pause_detail"],
        "effort": settings.get("effort"),
        "nodes_total": 0,
        "nodes_max": settings.get("effort_budget", {}).get("max_nodes", 0),
        "running_count": 0,
        "spent_usd": r["spent_usd"],
        "spend_approximate": bool(r["spend_approximate"]),
        "spending_limit_usd": r["spending_limit_usd"],
        "disk_bytes": 0,
        "run_seconds": 0,
        "last_activity_at": r["last_activity_at"],
        "summary": None,
    }


async def _row(db: Database, id: str) -> Row:
    rows = await db.read("SELECT * FROM investigations WHERE id = ?", [id])
    if not rows:
        raise HTTPException(404, "No such investigation")
    return rows[0]


@router.get("")
async def list_investigations(db: Annotated[Database, Depends(get_db)]) -> list[dict]:
    rows = await db.read("SELECT * FROM investigations ORDER BY last_activity_at DESC, id")
    return [list_row(r) for r in rows]


@router.post("", status_code=202)
async def create_investigation(
    body: CreateInvestigation, engine: Annotated[Engine, Depends(get_engine)]
) -> CommandAck:
    return await engine.create_investigation(body.id, body.prompt, body.settings)


@router.delete("/{id}", status_code=204)
async def delete_investigation(id: str, engine: Annotated[Engine, Depends(get_engine)]) -> Response:
    await engine.delete_investigation(id)
    return Response(status_code=204)


@router.get("/{id}")
async def snapshot(id: str, db: Annotated[Database, Depends(get_db)]) -> dict:
    r = await _row(db, id)
    investigation = list_row(r) | {"settings": json.loads(r["settings"]), "root_goal": None}
    return {
        "seq": r["last_seq"],
        "investigation": investigation,
        "nodes": [],
        "instructions": [],
        "premises": [],
        "schedule": {"order": [], "reasons": {}, "slots": 0},
        "focus_node_id": None,
        "plan_version": 0,
    }


@router.get("/{id}/events")
async def events(
    id: str,
    db: Annotated[Database, Depends(get_db)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int | None, Query(ge=1, le=10_000)] = None,
) -> list[dict]:
    await _row(db, id)
    return [e.model_dump(mode="json") for e in await eventlog.read(db, id, after, limit)]
