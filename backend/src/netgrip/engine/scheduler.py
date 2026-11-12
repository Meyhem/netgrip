"""Which nodes may start, in what order, and why the others wait (G2, G3). Pure."""

from dataclasses import dataclass, field

from netgrip.store.db import Database

FINISHED = ("Completed", "Failed", "Rejected")
PREMISE_CHECK = "Premise check"


@dataclass(frozen=True)
class GraphNode:
    id: str
    status: str
    kind: str
    depth: int
    seq: int
    parent_id: str | None
    depends_on: tuple[str, ...] = ()
    inclusion: str = "Included"
    paused: bool = False


@dataclass(frozen=True)
class Schedule:
    order: list[str]  # eligible node ids in start order
    reasons: dict[str, str] = field(default_factory=dict)  # node id -> wait reason
    slots: int = 0


def _children(graph: list[GraphNode]) -> dict[str, list[GraphNode]]:
    kids: dict[str, list[GraphNode]] = {}
    for n in graph:
        if n.parent_id is not None and n.inclusion == "Included":
            kids.setdefault(n.parent_id, []).append(n)
    return kids


def _blocking_dependency(n: GraphNode, by_id: dict[str, GraphNode]) -> str | None:
    return next((d for d in n.depends_on if d in by_id and by_id[d].status != "Completed"), None)


def eligible(graph: list[GraphNode]) -> list[str]:
    """Pending, Included, not paused, every dependency Completed (G2); or a coordinator
    Waiting on children whose included children have all finished, to aggregate (G3).
    The root is not scheduled: synthesis answers it. Premise checks first, then by depth,
    then by creation."""
    by_id = {n.id: n for n in graph}
    kids = _children(graph)
    out = []
    for n in graph:
        if n.parent_id is None or n.inclusion != "Included" or n.paused:
            continue
        if n.status == "Pending" and _blocking_dependency(n, by_id) is None:
            out.append(n)
        elif n.status == "Waiting on children" and all(
            k.status in FINISHED for k in kids.get(n.id, [])
        ):
            out.append(n)
    out.sort(key=lambda n: (n.kind != PREMISE_CHECK, n.depth, n.seq))
    return [n.id for n in out]


def schedule(graph: list[GraphNode], slots: int) -> Schedule:
    """`order` is every eligible node; those past `slots` wait for a `slot`. Others wait on a
    `dependency:<id>`, the `orchestrator` (proposed, not yet gated) or are `paused`."""
    order = eligible(graph)
    by_id = {n.id: n for n in graph}
    reasons = {nid: "slot" for nid in order[max(slots, 0) :]}
    for n in graph:
        if n.parent_id is None or n.inclusion != "Included" or n.id in order:
            continue
        if n.status == "Proposed":
            reasons[n.id] = "orchestrator"
        elif n.status == "Pending" and n.paused:
            reasons[n.id] = "paused"
        elif n.status == "Pending" and (dep := _blocking_dependency(n, by_id)):
            reasons[n.id] = f"dependency:{dep}"
    return Schedule(order=order, reasons=reasons, slots=slots)


async def load_graph(db: Database, investigation_id: str) -> list[GraphNode]:
    rows = await db.read(
        "SELECT id, status, kind, depth, seq, parent_id, inclusion FROM nodes"
        " WHERE investigation_id = ? ORDER BY seq",
        [investigation_id],
    )
    deps: dict[str, list[str]] = {}
    for r in await db.read(
        "SELECT node_id, depends_on_id FROM node_deps WHERE investigation_id = ?",
        [investigation_id],
    ):
        deps.setdefault(r["node_id"], []).append(r["depends_on_id"])
    return [
        GraphNode(
            id=r["id"],
            status=r["status"],
            kind=r["kind"],
            depth=r["depth"],
            seq=r["seq"],
            parent_id=r["parent_id"],
            depends_on=tuple(deps.get(r["id"], ())),
            inclusion=r["inclusion"],
            paused=r["status"] == "Paused",
        )  # fmt: skip
        for r in rows
    ]
