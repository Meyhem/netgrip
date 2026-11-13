"""The stored report and its Markdown export (Phase 8)."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse

from netgrip.api.deps import get_db
from netgrip.api.nodes import _source_json
from netgrip.report.markdown import filename, to_markdown
from netgrip.report.model import Report
from netgrip.store.db import Database

router = APIRouter(prefix="/api/investigations")


NO_REPORT = {"code": "no_report", "message": "There is no report yet"}


async def load_report(db: Database, id: str) -> tuple[Report | None, str]:
    """The stored report (None before one exists) and the prompt; 404 for an unknown id."""
    rows = await db.read("SELECT prompt FROM investigations WHERE id = ?", [id])
    if not rows:
        raise HTTPException(404, "No such investigation")
    stored = await db.read("SELECT body FROM reports WHERE investigation_id = ?", [id])
    body = Report.model_validate_json(stored[0]["body"]) if stored else None
    return body, rows[0]["prompt"]


async def cited_claims(db: Database, id: str, report: Report) -> dict[str, dict[str, Any]]:
    """Every claim the report cites: text, status, sources, and the node that produced it with
    its path from the root, so the screen needs no second request."""
    wanted = {i for s in report.sections for st in s.statements for i in st.claim_ids}
    nodes = {
        n["id"]: n for n in await db.read("SELECT * FROM nodes WHERE investigation_id = ?", [id])
    }
    sources = {
        s["id"]: _source_json(s)
        for s in await db.read("SELECT * FROM sources WHERE investigation_id = ?", [id])
    }
    out: dict[str, dict[str, Any]] = {}
    for r in await db.read("SELECT * FROM claims WHERE investigation_id = ? ORDER BY seq", [id]):
        if r["id"] not in wanted:
            continue
        path, node = [], nodes.get(r["node_id"])
        while node is not None and len(path) <= len(nodes):
            path.insert(0, {"id": node["id"], "display_id": node["display_id"],
                            "question": node["question"]})  # fmt: skip
            node = nodes.get(node["parent_id"])
        out[r["id"]] = {
            "id": r["id"], "node_id": r["node_id"], "text": r["text"], "status": r["status"],
            "supporting": [], "contradicting": [],
            "node_display_id": path[-1]["display_id"] if path else None, "path": path,
        }  # fmt: skip
    for s in await db.read(
        "SELECT claim_id, source_id, stance FROM claim_sources WHERE investigation_id = ?"
        " ORDER BY source_id",
        [id],
    ):
        claim = out.get(s["claim_id"])
        if claim is not None and s["source_id"] in sources:
            side = "supporting" if s["stance"] == "supports" else "contradicting"
            claim[side].append(sources[s["source_id"]])
    return out


@router.get("/{id}/report", response_model=None)
async def report(id: str, db: Annotated[Database, Depends(get_db)]) -> Response | dict:
    stored, _ = await load_report(db, id)
    if stored is None:
        return JSONResponse(NO_REPORT, status_code=404)
    return stored.model_dump(mode="json") | {"claims": await cited_claims(db, id, stored)}


@router.get("/{id}/report.md", response_model=None)
async def report_markdown(id: str, db: Annotated[Database, Depends(get_db)]) -> Response:
    stored, prompt = await load_report(db, id)
    if stored is None:
        return JSONResponse(NO_REPORT, status_code=404)
    body = to_markdown(stored, await cited_claims(db, id, stored), prompt)
    return Response(
        body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename(prompt)}"'},
    )
