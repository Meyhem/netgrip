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


# The Paused line of a list row, by cause (the frontend's PAUSE_REASON says the same).
PAUSE_REASON = {
    "user": "Paused by you.",
    "spending_limit": "Reached the spending limit.",
    "model_unavailable": "The model service stopped responding.",
    "search_unavailable": "Web search stopped responding.",
    "key_rejected": "A key was rejected.",
    "credit_exhausted": "The model account ran out of credit.",
}
TERMINAL_UNAPPROVED = ("Proposed", "Rejected")


def summarise(state: str, pause_cause: str | None, nodes: list, premises: list) -> dict:
    """The derived part of a list row, from the nodes (in seq order) and premises. The
    frontend's `derive` (frontend/src/state/summary.ts) computes the same from the snapshot.

    - running_count: nodes Running, while the investigation is Running.
    - nodes_total: nodes below the root that were approved (what the node limit counts).
    - summary: Running, the first running node's activity ("D1 Searching"); Paused, the
      cause; then each refuted premise ("Premise refuted: <text>"); joined by " · "."""
    running = [n for n in nodes if n["status"] == "Running"] if state == "Running" else []
    parts: list[str] = []
    if state == "Running":
        live = next((n for n in running if n["activity"]), None)
        if live is not None:
            parts.append(f"{live['display_id']} {live['activity']}")
    elif state == "Paused":
        parts.append(PAUSE_REASON.get(pause_cause or "", "Paused."))
    parts += [f"Premise refuted: {p['text']}" for p in premises if p["outcome"] == "refuted"]
    return {
        "running_count": len(running),
        "nodes_total": sum(
            1 for n in nodes if n["depth"] >= 1 and n["status"] not in TERMINAL_UNAPPROVED
        ),
        "summary": " · ".join(parts) or None,
    }


def list_row(r: Row, nodes: list, premises: list) -> dict[str, Any]:
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
    } | summarise(r["state"], r["pause_cause"], nodes, premises)


async def _row_parts(db: Database, ids: list[str]) -> tuple[dict, dict]:
    """Nodes (seq order) and premises per investigation, for `summarise`."""
    nodes: dict[str, list] = {i: [] for i in ids}
    premises: dict[str, list] = {i: [] for i in ids}
    for n in await db.read(
        "SELECT investigation_id, display_id, status, activity, depth FROM nodes ORDER BY seq"
    ):
        nodes.setdefault(n["investigation_id"], []).append(n)
    for p in await db.read("SELECT investigation_id, text, outcome FROM premises ORDER BY seq"):
        premises.setdefault(p["investigation_id"], []).append(p)
    return nodes, premises


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
        "brief": _load(n["brief"]),
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
    nodes, premises = await _row_parts(db, [r["id"] for r in rows])
    return [list_row(r, nodes[r["id"]], premises[r["id"]]) for r in rows]


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
    node_rows = await db.read("SELECT * FROM nodes WHERE investigation_id = ? ORDER BY seq", [id])
    premise_rows = await db.read(
        "SELECT * FROM premises WHERE investigation_id = ? ORDER BY seq", [id]
    )
    investigation = list_row(r, node_rows, premise_rows) | {
        "settings": json.loads(r["settings"]),
        "root_goal": r["root_goal"],
    }
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
        "schedule": await _schedule(db, id),
        "focus_node_id": None,
        "plan_version": version[0]["v"],
    }


async def _schedule(db: Database, id: str) -> dict:
    """The last `schedule.updated`, as it was emitted."""
    rows = await db.read(
        "SELECT data FROM events WHERE investigation_id = ? AND type = 'schedule.updated'"
        " ORDER BY seq DESC LIMIT 1",
        [id],
    )
    if not rows:
        return {"order": [], "reasons": {}, "slots": 0}
    d = json.loads(rows[0]["data"])
    return {"order": d["order"], "reasons": d["reasons"], "slots": d["slots"]}


@router.get("/{id}/events")
async def events(
    id: str,
    db: Annotated[Database, Depends(get_db)],
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int | None, Query(ge=1, le=10_000)] = None,
) -> list[dict]:
    await _row(db, id)
    return [e.model_dump(mode="json") for e in await eventlog.read(db, id, after, limit)]
