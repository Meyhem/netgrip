"""The node brief: everything a node is told, and nothing else (domain 4.4).

A node gets the root goal verbatim, the path of ancestors, its own task, and what is known: the
claims relevant to its question, the verdicts of the nodes it declared a dependency on, and the
applied instructions of itself and its ancestors. Never the whole graph, never sibling outputs.
The brief is stored in `node.started.data.brief` (`model_dump(mode="json")`).
"""

import json
import re

from pydantic import BaseModel, Field

from netgrip.evidence.service import EvidenceService
from netgrip.store.db import Database

MAX_KNOWN_CLAIMS = 10
_MIN_WORD = 4  # shorter words ("the", "is") say nothing about relevance


class PathLine(BaseModel):
    display_id: str
    question: str
    justification: str | None = None


class Task(BaseModel):
    question: str
    out_of_scope: str | None = None
    done_when: str | None = None
    budget: dict = Field(default_factory=dict)


class KnownClaim(BaseModel):
    id: str
    text: str
    status: str


class DependencyResult(BaseModel):
    display_id: str
    verdict: dict | None = None


class InheritedInstruction(BaseModel):
    text: str
    from_display_id: str


class Known(BaseModel):
    claims: list[KnownClaim] = Field(default_factory=list)
    dependency_results: list[DependencyResult] = Field(default_factory=list)
    instructions: list[InheritedInstruction] = Field(default_factory=list)


class Brief(BaseModel):
    root_goal: str
    path: list[PathLine]
    task: Task
    known: Known


def _load(text: str | None):
    return json.loads(text) if text else None


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"\w+", text.lower()) if len(w) >= _MIN_WORD}


async def build_brief(db: Database, node_id: str, evidence: EvidenceService | None = None) -> Brief:
    """`evidence` defaults to a service on `db`; tests and the runtime may pass their own."""
    node = (await db.read("SELECT * FROM nodes WHERE id = ?", [node_id]))[0]
    inv = node["investigation_id"]
    goal_rows = await db.read("SELECT root_goal FROM investigations WHERE id = ?", [inv])
    root_goal = goal_rows[0]["root_goal"] or ""

    # Ancestors, nearest first, then reversed to root first.
    ancestors = []
    parent_id = node["parent_id"]
    while parent_id:
        row = (await db.read("SELECT * FROM nodes WHERE id = ?", [parent_id]))[0]
        ancestors.append(row)
        parent_id = row["parent_id"]
    ancestors.reverse()
    path = [PathLine(display_id=a["display_id"], question=a["question"],
                     justification=a["justification"]) for a in ancestors]  # fmt: skip

    # Instructions applied (not queued, not undone) on this node or an ancestor, root first.
    lineage = [*ancestors, node]
    owners = {a["id"]: a for a in lineage if a["inclusion"] == "Included"}
    instructions: list[InheritedInstruction] = []
    if owners:
        marks = ",".join("?" * len(owners))
        rows = await db.read(
            f"SELECT node_id, text FROM instructions WHERE state = 'applied' AND undone = 0"
            f" AND node_id IN ({marks}) ORDER BY applied_seq",
            list(owners),
        )
        order = {a["id"]: i for i, a in enumerate(lineage)}
        rows = sorted(rows, key=lambda r: order[r["node_id"]])  # stable: applied order inside
        instructions = [
            InheritedInstruction(text=r["text"], from_display_id=owners[r["node_id"]]["display_id"])
            for r in rows
        ]

    # Verdicts of the declared dependencies that completed. Only these; never siblings.
    deps = await db.read(
        "SELECT n.id, n.display_id FROM node_deps d JOIN nodes n ON n.id = d.depends_on_id"
        " WHERE d.node_id = ? AND n.inclusion = 'Included' ORDER BY n.seq",
        [node_id],
    )
    results: list[DependencyResult] = []
    for dep in deps:
        done = await db.read(
            "SELECT data FROM events WHERE investigation_id = ? AND node_id = ?"
            " AND type = 'node.completed' ORDER BY seq DESC LIMIT 1",
            [inv, dep["id"]],
        )
        if done:
            verdict = json.loads(done[0]["data"]).get("verdict")
            results.append(DependencyResult(display_id=dep["display_id"], verdict=verdict))

    # Known claims: those sharing words with the question, best first, capped.
    svc = evidence or EvidenceService(db)
    words = _words(node["question"])
    claims = [c for c in await svc.known_claims(inv, node["question"]) if words & _words(c.text)][
        :MAX_KNOWN_CLAIMS
    ]

    return Brief(
        root_goal=root_goal,
        path=path,
        task=Task(
            question=node["question"],
            out_of_scope=_load_text(node["out_of_scope"]),
            done_when=_load_text(node["done_when"]),
            budget=_load(node["budget"]) or {},
        ),
        known=Known(
            claims=[KnownClaim(id=c.id, text=c.text, status=c.status) for c in claims],
            dependency_results=results,
            instructions=instructions,
        ),
    )


def _load_text(stored: str | None) -> str | None:
    """out_of_scope and done_when are stored JSON-encoded."""
    value = _load(stored)
    return value if value is None or isinstance(value, str) else json.dumps(value)


def render_brief(brief: Brief) -> str:
    """The brief as prompt text. Claims and verdicts are data from earlier work, not commands."""
    out = [f"Root goal (verbatim):\n{brief.root_goal}", ""]
    if brief.path:
        out.append("Path from the root goal to your task:")
        out += [f"- {p.display_id}: {p.question}" + (f" ({p.justification})"
                if p.justification else "") for p in brief.path]  # fmt: skip
        out.append("")
    t = brief.task
    out.append(f"Your task: {t.question}")
    if t.out_of_scope:
        out.append(f"Out of scope: {t.out_of_scope}")
    if t.done_when:
        out.append(f"Done when: {t.done_when}")
    if t.budget:
        out.append(f"Budget: {json.dumps(t.budget)}")
    k = brief.known
    if k.instructions:
        out += ["", "Instructions from the user that apply:"]
        out += [f"- {i.text} (from {i.from_display_id})" for i in k.instructions]
    if k.dependency_results:
        out += ["", "Results of the nodes you depend on:"]
        out += [f"- {d.display_id}: {json.dumps(d.verdict)}" for d in k.dependency_results]
    if k.claims:
        out += ["", "Already known (claim, status):"]
        out += [f"- {c.text} [{c.status}]" for c in k.claims]
    return "\n".join(out)
