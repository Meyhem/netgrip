"""Node detail and stored page queries (Phase 5): everything about one node, on demand."""

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from netgrip.api.deps import get_db, get_engine
from netgrip.api.investigations import instruction_json, node_json
from netgrip.engine.engine import Engine
from netgrip.store.db import Database, Row

router = APIRouter(prefix="/api/investigations")

UNAPPROVED = ("Proposed", "Rejected")
UNFINISHED = ("Pending", "Running", "Waiting on children", "Paused")


def _load(text: str | None) -> Any:
    return None if text is None else json.loads(text)


async def _investigation(db: Database, id: str) -> Row:
    rows = await db.read("SELECT * FROM investigations WHERE id = ?", [id])
    if not rows:
        raise HTTPException(404, "No such investigation")
    return rows[0]


def _source_json(s: Row) -> dict[str, Any]:
    return {
        "id": s["id"],
        "url": s["url"],
        "title": s["title"],
        "page_version_id": s["page_version_id"],
        "credibility": s["credibility"],
        "published_at": s["published_at"],
        "origin_key": s["origin_key"],
    }


async def _claims(db: Database, inv: str, node_id: str) -> list[dict]:
    """The claims this node added or contributed to, each followed to the claim it was merged
    into, with their supporting and contradicting sources."""
    rows = await db.read("SELECT * FROM claims WHERE investigation_id = ? ORDER BY seq", [inv])
    by_id = {r["id"]: r for r in rows}
    touched = await db.read(
        "SELECT data FROM events WHERE investigation_id = ? AND node_id = ?"
        " AND type IN ('claim.added', 'claim.updated') ORDER BY seq",
        [inv, node_id],
    )
    wanted: set[str] = set()
    for t in touched:
        claim = by_id.get(json.loads(t["data"])["claim_id"])
        seen: set[str] = set()
        while claim is not None and claim["merged_into"] and claim["id"] not in seen:
            seen.add(claim["id"])
            claim = by_id.get(claim["merged_into"], claim)
        if claim is not None:
            wanted.add(claim["id"])
    if not wanted:
        return []
    sources = {
        s["id"]: _source_json(s)
        for s in await db.read("SELECT * FROM sources WHERE investigation_id = ?", [inv])
    }
    stances = await db.read(
        "SELECT claim_id, source_id, stance FROM claim_sources WHERE investigation_id = ?"
        " ORDER BY source_id",
        [inv],
    )
    out = {
        r["id"]: {"id": r["id"], "node_id": r["node_id"], "text": r["text"],
                  "status": r["status"], "supporting": [], "contradicting": []}
        for r in rows if r["id"] in wanted
    }  # fmt: skip
    for s in stances:
        claim = out.get(s["claim_id"])
        if claim is not None and s["source_id"] in sources:
            side = "supporting" if s["stance"] == "supports" else "contradicting"
            claim[side].append(sources[s["source_id"]])
    return list(out.values())


def _trail_json(t: Row) -> dict[str, Any]:
    return {
        "step": t["step"],
        "name": t["name"],
        "kind": t["kind"],
        "activity": t["activity"],
        "detail": t["detail"],
        "summary": t["summary"],
        "started_at": t["started_at"],
        "ended_at": t["ended_at"],
        "route": t["route"],
        "page_version_id": t["page_version_id"],
        "retry": _load(t["retry"]),
        "instruction_applied": json.loads(t["instruction_applied"]),
    }


async def _instructions(db: Database, inv: str, lineage: list[Row]) -> dict[str, list]:
    """Inherited: the ancestors' instructions, root first, each ancestor's oldest first. Own:
    the node's, oldest first."""
    rows = await db.read(
        "SELECT * FROM instructions WHERE investigation_id = ? ORDER BY queued_seq", [inv]
    )
    node = lineage[-1]
    inherited = [
        instruction_json(i) | {"from_display_id": a["display_id"]}
        for a in lineage[:-1]
        for i in rows
        if i["node_id"] == a["id"]
    ]
    own = [instruction_json(i) for i in rows if i["node_id"] == node["id"]]
    return {"inherited": inherited, "own": own}


def _decision(status: str) -> str:
    return {"Proposed": "pending", "Rejected": "rejected"}.get(status, "approved")


def _branch(node: Row, nodes: list[Row], settings: dict) -> dict[str, Any]:
    """The node with its descendants: spend, approved nodes below it against the child
    allowance of the branch's approved nodes, the deepest approved level against the depth
    limit, and how many unfinished included nodes an instruction here would reach."""
    children: dict[str, list[Row]] = {}
    for n in nodes:
        children.setdefault(n["parent_id"], []).append(n)
    branch, todo = [], [node]
    while todo:
        n = todo.pop()
        branch.append(n)
        todo += children.get(n["id"], [])
    approved = [n for n in branch if n["status"] not in UNAPPROVED]
    return {
        "spent_usd": sum(n["spent_usd"] for n in branch),
        "nodes": sum(1 for n in approved if n["id"] != node["id"]),
        "nodes_max": sum(int((_load(n["budget"]) or {}).get("child_nodes", 0)) for n in approved),
        "depth": max((n["depth"] for n in approved), default=node["depth"]),
        "depth_max": settings.get("effort_budget", {}).get("max_depth", 0),
        "reach": sum(
            1 for n in branch if n["inclusion"] == "Included" and n["status"] in UNFINISHED
        ),
    }


@router.get("/{id}/nodes/{node_id}")
async def node_detail(id: str, node_id: str, db: Annotated[Database, Depends(get_db)]) -> dict:
    inv = await _investigation(db, id)
    nodes = await db.read("SELECT * FROM nodes WHERE investigation_id = ? ORDER BY seq", [id])
    by_id = {n["id"]: n for n in nodes}
    node = by_id.get(node_id)
    if node is None:
        raise HTTPException(404, "No such node")
    lineage = [node]
    while lineage[0]["parent_id"] in by_id and len(lineage) <= len(nodes):
        lineage.insert(0, by_id[lineage[0]["parent_id"]])
    deps = await db.read(
        "SELECT depends_on_id FROM node_deps WHERE node_id = ? ORDER BY depends_on_id", [node_id]
    )
    trail = await db.read("SELECT * FROM node_steps WHERE node_id = ? ORDER BY step", [node_id])
    completed = await db.read(
        "SELECT data FROM events WHERE investigation_id = ? AND node_id = ?"
        " AND type = 'node.completed' ORDER BY seq DESC LIMIT 1",
        [id, node_id],
    )
    return {
        "node": node_json(node, [d["depends_on_id"] for d in deps]),
        # As the node received it in its last node.started; null for a node that never started
        # (a coordinator from the plan waits on its children without starting).
        "brief": _load(node["brief"]),
        "claims": await _claims(db, id, node_id),
        "trail": [_trail_json(t) for t in trail],
        "instructions": await _instructions(db, id, lineage),
        "open_questions": json.loads(completed[0]["data"]).get("open_questions", [])
        if completed
        else [],
        "proposals": [
            {
                "node_id": n["id"],
                "display_id": n["display_id"],
                "question": n["question"],
                "decision": _decision(n["status"]),
                "reason": n["rejection_reason"],
            }
            for n in nodes
            if n["proposed_by"] == node_id
        ],
        "branch": _branch(node, nodes, json.loads(inv["settings"])),
    }


@router.get("/{id}/pages/{page_version_id}")
async def stored_page(
    id: str, page_version_id: str, engine: Annotated[Engine, Depends(get_engine)]
) -> dict:
    """The cleaned text of a page version this investigation used; 404 for any other."""
    db = engine.db
    rows = await db.read(
        "SELECT v.url, v.title, v.fetched_at FROM investigation_pages ip"
        " JOIN page_versions v ON v.id = ip.page_version_id"
        " WHERE ip.investigation_id = ? AND ip.page_version_id = ?",
        [id, page_version_id],
    )
    if not rows:
        raise HTTPException(404, "No such page in this investigation")
    try:
        text = await engine.pages.read_text(page_version_id)
    except (KeyError, FileNotFoundError):
        raise HTTPException(404, "The stored page is missing") from None
    r = rows[0]
    return {"url": r["url"], "title": r["title"], "fetched_at": r["fetched_at"], "text": text}
