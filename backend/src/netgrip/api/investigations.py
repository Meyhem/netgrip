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


def _load(text: str | None) -> Any:
    return None if text is None else json.loads(text)


def node_json(n: Row, depends_on: list[str]) -> dict[str, Any]:
    return {
        "id": n["id"],
        "display_id": n["display_id"],
        "parent_id": n["parent_id"],
        "kind": n["kind"],
        "question": n["question"],
        "justification": n["justification"],
        "out_of_scope": _load(n["out_of_scope"]),
        "done_when": _load(n["done_when"]),
        "depth": n["depth"],
        "status": n["status"],
        "inclusion": n["inclusion"],
        "budget": _load(n["budget"]),
        "activity": n["activity"],
        "verdict": _load(n["verdict"]),
        "brief": n["brief"],
        "spent_usd": n["spent_usd"],
        "instruction_count": n["instruction_count"],
        "plan_version_added": n["plan_version_added"],
        "proposed_by": n["proposed_by"],
        "depends_on": depends_on,
    }


def instruction_json(i: Row) -> dict[str, Any]:
    return {
        "id": i["id"],
        "node_id": i["node_id"],
        "text": i["text"],
        "state": i["state"],
        "queued_seq": i["queued_seq"],
        "applied_seq": i["applied_seq"],
        "diff": _load(i["diff"]),
        "undone": bool(i["undone"]),
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
    investigation = list_row(r) | {
        "settings": json.loads(r["settings"]),
        "root_goal": r["root_goal"],
    }
    node_rows = await db.read("SELECT * FROM nodes WHERE investigation_id = ? ORDER BY seq", [id])
    deps: dict[str, list[str]] = {}
    for d in await db.read(
        "SELECT node_id, depends_on_id FROM node_deps WHERE investigation_id = ?"
        " ORDER BY node_id, depends_on_id",
        [id],
    ):
        deps.setdefault(d["node_id"], []).append(d["depends_on_id"])
    instruction_rows = await db.read(
        "SELECT * FROM instructions WHERE investigation_id = ? ORDER BY queued_seq", [id]
    )
    premise_rows = await db.read(
        "SELECT * FROM premises WHERE investigation_id = ? ORDER BY seq", [id]
    )
    version = await db.read(
        "SELECT COALESCE(MAX(version), 0) AS v FROM plan_versions WHERE investigation_id = ?", [id]
    )
    return {
        "seq": r["last_seq"],
        "investigation": investigation,
        "nodes": [node_json(n, deps.get(n["id"], [])) for n in node_rows],
        "instructions": [instruction_json(i) for i in instruction_rows],
        "premises": [
            {"id": p["id"], "text": p["text"], "node_id": p["node_id"], "outcome": p["outcome"]}
            for p in premise_rows
        ],
        "plan_failed": r["plan_failed_reason"],
        "schedule": {"order": [], "reasons": {}, "slots": 0},
        "focus_node_id": None,
        "plan_version": version[0]["v"],
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
