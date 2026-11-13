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
    failure_handled: bool = False  # Failed, and the decision to leave it Failed is recorded


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


def _settled(n: GraphNode) -> bool:
    """A dependency no longer holds its dependants back: Completed, Rejected (it will never
    run), or Failed and left Failed (no retry coming). The dependant's brief then names it as
    failed, with its reason."""
    return n.status in ("Completed", "Rejected") or (n.status == "Failed" and n.failure_handled)


def _blocking_dependency(n: GraphNode, by_id: dict[str, GraphNode]) -> str | None:
    return next((d for d in n.depends_on if d in by_id and not _settled(by_id[d])), None)


def branch_ids(graph: list[GraphNode], node_id: str) -> list[str]:
    """`node_id` and every node below it (any inclusion), in creation order."""
    kids: dict[str, list[str]] = {}
    for n in graph:
        if n.parent_id is not None:
            kids.setdefault(n.parent_id, []).append(n.id)
    out, todo = [], [node_id]
    while todo:
        cur = todo.pop()
        out.append(cur)
        todo.extend(kids.get(cur, []))
    order = {n.id: i for i, n in enumerate(graph)}
    return sorted(out, key=lambda i: order.get(i, 0))


def excluded(n: GraphNode, by_id: dict[str, GraphNode]) -> bool:
    """Not Included itself, or below a node that is not (a step in flight may still have
    proposed a child under a branch that was ignored meanwhile)."""
    seen = set()
    while n is not None and n.id not in seen:
        if n.inclusion != "Included":
            return True
        seen.add(n.id)
        n = by_id.get(n.parent_id) if n.parent_id else None
    return False


def eligible(graph: list[GraphNode], focus: str | None = None) -> list[str]:
    """Pending, Included, not paused, every dependency Completed or left Failed (G2); or a
    coordinator Waiting on children whose included children have all finished, to aggregate
    (G3). With `focus`, only that node's branch (S5).
    The root is not scheduled: synthesis answers it. Premise checks first, then by depth,
    then by creation."""
    by_id = {n.id: n for n in graph}
    kids = _children(graph)
    inside = set(branch_ids(graph, focus)) if focus else None
    out = []
    for n in graph:
        if n.parent_id is None or n.paused or excluded(n, by_id):
            continue
        if inside is not None and n.id not in inside:
            continue
        if n.status == "Pending" and _blocking_dependency(n, by_id) is None:
            out.append(n)
        elif n.status == "Waiting on children" and all(
            k.status in FINISHED for k in kids.get(n.id, [])
        ):
            out.append(n)
    out.sort(key=lambda n: (n.kind != PREMISE_CHECK, n.depth, n.seq))
    return [n.id for n in out]


def schedule(graph: list[GraphNode], slots: int, focus: str | None = None) -> Schedule:
    """`order` is every eligible node; those past `slots` wait for a `slot`. Others wait on a
    `dependency:<id>`, the `orchestrator` (proposed, not yet gated), `focus:<id>` (the user
    runs only another branch) or are `paused`."""
    order = eligible(graph, focus)
    by_id = {n.id: n for n in graph}
    inside = set(branch_ids(graph, focus)) if focus else None
    reasons = {nid: "slot" for nid in order[max(slots, 0) :]}
    outside = eligible(graph) if focus else []
    for n in graph:
        if n.parent_id is None or excluded(n, by_id) or n.id in order:
            continue
        if n.status == "Proposed":
            reasons[n.id] = "orchestrator"
        elif n.paused:
            reasons[n.id] = "paused"
        elif (
            inside is not None
            and n.id not in inside
            and (n.id in outside or n.status in ("Pending", "Waiting on children"))
        ):
            reasons[n.id] = f"focus:{focus}"
        elif n.status == "Pending" and (dep := _blocking_dependency(n, by_id)):
            reasons[n.id] = f"dependency:{dep}"
    return Schedule(order=order, reasons=reasons, slots=slots)


async def load_graph(db: Database, investigation_id: str) -> list[GraphNode]:
    rows = await db.read(
        "SELECT id, status, kind, depth, seq, parent_id, inclusion, failure_handled FROM nodes"
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
            failure_handled=bool(r["failure_handled"]),
        )  # fmt: skip
        for r in rows
    ]
