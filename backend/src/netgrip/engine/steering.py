"""The user's interventions (domain 4.9). Each is a command handler that checks the current
state and records events; the runtime applies them at step boundaries (E4). Nothing here
touches a running step: it finishes, and the node's next boundary sees the new state."""

import json
import math
import uuid

from netgrip.boundary.commands import Command, CommandRejected
from netgrip.boundary.events import EventDraft
from netgrip.engine.budget import allocate_budget
from netgrip.engine.engine import Engine, handles
from netgrip.engine.scheduler import GraphNode, branch_ids
from netgrip.store.db import Tx
from netgrip.store.projections import PAUSABLE
from netgrip.store.settings import Effort

STEERABLE = ("Running", "Paused", "Stopped")


async def load_graph_tx(tx: Tx, investigation_id: str) -> list[GraphNode]:
    rows = await tx.fetchall(
        "SELECT id, status, kind, depth, seq, parent_id, inclusion, failure_handled FROM nodes"
        " WHERE investigation_id = ? ORDER BY seq",
        [investigation_id],
    )
    return [
        GraphNode(
            id=r["id"],
            status=r["status"],
            kind=r["kind"],
            depth=r["depth"],
            seq=r["seq"],
            parent_id=r["parent_id"],
            inclusion=r["inclusion"],
            paused=r["status"] == "Paused",
            failure_handled=bool(r["failure_handled"]),
        )  # fmt: skip
        for r in rows
    ]


async def _target(tx: Tx, cmd: Command, *, states: tuple[str, ...] = STEERABLE) -> dict:
    """The node a node command aims at, in an investigation that may be steered. The root is
    steered with the investigation's own controls."""
    if cmd.node_id is None:
        raise CommandRejected("node_required", "This command needs a node")
    inv = await tx.fetchone(
        "SELECT state, settings, focus_node_id FROM investigations WHERE id = ?",
        [cmd.investigation_id],
    )
    node = await tx.fetchone(
        "SELECT * FROM nodes WHERE id = ? AND investigation_id = ?",
        [cmd.node_id, cmd.investigation_id],
    )
    if node is None:
        raise CommandRejected("not_found", "No such node")
    if node["parent_id"] is None:
        raise CommandRejected("use_investigation_controls", "Use the investigation's controls")
    if inv["state"] not in states:
        raise CommandRejected("wrong_state", f"Not possible while {inv['state']}")
    return {"node": dict(node), "inv": dict(inv)}


def _nudge(engine: Engine, tx: Tx, inv: str) -> None:
    """Let a live runtime look again (a new state may free or stop work)."""

    def wake() -> None:
        rt = engine.runtimes.get(inv)
        if rt is not None and rt.active:
            rt.wake()

    tx.after_commit(wake)


def _user(type: str, data: dict, node_id: str | None = None) -> EventDraft:
    return EventDraft(type=type, actor="user", node_id=node_id, data=data)


# --- Task 1: ignore, restore, pause and resume a branch ----------------------------------------


@handles("ignore_branch")
async def _ignore_branch(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """The branch leaves the research: nothing of it starts, its claims leave the briefs and
    the report. Everything stays stored and `restore_branch` brings it back. Running nodes
    of the branch finish their step and go back to Pending (the runtime, at the boundary)."""
    t = await _target(tx, cmd)
    graph = await load_graph_tx(tx, cmd.investigation_id)
    ids = [
        i for i in branch_ids(graph, cmd.node_id)
        if next(n for n in graph if n.id == i).inclusion == "Included"
    ]  # fmt: skip
    if t["node"]["inclusion"] != "Included" or not ids:
        return []  # already out: a repeated ignore changes nothing
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("node.inclusion_changed", {"node_ids": ids, "inclusion": "Ignored", "by": "user"},
                  cmd.node_id)]  # fmt: skip


@handles("restore_branch")
async def _restore_branch(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Back to Included, also for a Superseded branch: the target and the nodes below it that
    were taken out with it (same actor and instruction). Completed nodes keep their output."""
    t = await _target(tx, cmd)
    node = t["node"]
    if node["inclusion"] == "Included":
        return []
    rows = await tx.fetchall(
        "SELECT id, inclusion, excluded_by, excluded_instruction_id FROM nodes"
        " WHERE investigation_id = ?",
        [cmd.investigation_id],
    )
    graph = await load_graph_tx(tx, cmd.investigation_id)
    inside = set(branch_ids(graph, cmd.node_id))
    same = (node["excluded_by"], node["excluded_instruction_id"])
    ids = [
        r["id"] for r in rows
        if r["id"] in inside and r["inclusion"] != "Included"
        and (r["excluded_by"], r["excluded_instruction_id"]) == same
    ]  # fmt: skip
    data = {"node_ids": ids, "inclusion": "Included", "by": "user"}
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("node.inclusion_changed", data, cmd.node_id)]


@handles("pause_branch")
async def _pause_branch(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """The branch stops starting steps; the rest keeps running. A step in flight finishes."""
    await _target(tx, cmd)
    graph = await load_graph_tx(tx, cmd.investigation_id)
    by_id = {n.id: n for n in graph}
    ids = [i for i in branch_ids(graph, cmd.node_id) if by_id[i].status in PAUSABLE]
    if not ids:
        return []
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("node.paused", {"node_ids": ids}, cmd.node_id)]


@handles("resume_branch")
async def _resume_branch(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    await _target(tx, cmd)
    graph = await load_graph_tx(tx, cmd.investigation_id)
    by_id = {n.id: n for n in graph}
    ids = [i for i in branch_ids(graph, cmd.node_id) if by_id[i].status == "Paused"]
    if not ids:
        return []
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("node.resumed", {"node_ids": ids}, cmd.node_id)]


# --- Task 2: focus, go deeper, re-run, finish now ----------------------------------------------


@handles("run_only_branch")
async def _run_only_branch(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Nodes outside the branch wait (`focus:<id>`); their steps in flight finish."""
    t = await _target(tx, cmd)
    if t["inv"]["focus_node_id"] == cmd.node_id:
        return []
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("focus.changed", {"node_id": cmd.node_id}, cmd.node_id)]


@handles("run_everything")
async def _run_everything(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    inv = await tx.fetchone(
        "SELECT state, focus_node_id FROM investigations WHERE id = ?", [cmd.investigation_id]
    )
    if inv["state"] not in STEERABLE:
        raise CommandRejected("wrong_state", f"Not possible while {inv['state']}")
    if inv["focus_node_id"] is None:
        return []
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("focus.changed", {"node_id": None})]


def deeper_budget(old: dict, effort: Effort, depth: int) -> dict:
    """GO_DEEPER (B2): one level deeper, 1.5 times the child nodes and sources. A node at the
    deepest level had no child nodes: it gets those of the level it now sits at."""
    extra = int(old.get("depth_extra", 0)) + 1
    children = int(old.get("child_nodes", 0))
    if children > 0:
        children = math.ceil(children * 1.5)
    else:
        wider = effort.model_copy(update={"max_depth": effort.max_depth + extra})
        children = allocate_budget(wider, depth).child_nodes
    return {
        **old,
        "depth_extra": extra,
        "child_nodes": children,
        "sources": math.ceil(int(old.get("sources", 0)) * 1.5),
    }


@handles("go_deeper")
async def _go_deeper(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Raise the budget of the branch: more depth, child nodes and sources (B2). The node
    ceiling of the investigation rises by the child nodes added."""
    t = await _target(tx, cmd)
    if t["node"]["inclusion"] != "Included":
        raise CommandRejected("wrong_state", "Only an included branch can go deeper")
    effort = Effort.model_validate(json.loads(t["inv"]["settings"])["effort_budget"])
    graph = await load_graph_tx(tx, cmd.investigation_id)
    inside = set(branch_ids(graph, cmd.node_id))
    rows = await tx.fetchall(
        "SELECT id, depth, budget FROM nodes WHERE investigation_id = ? AND inclusion = 'Included'"
        " AND budget IS NOT NULL AND status NOT IN ('Proposed', 'Rejected')",
        [cmd.investigation_id],
    )
    budgets = {
        r["id"]: deeper_budget(json.loads(r["budget"]), effort, r["depth"])
        for r in rows if r["id"] in inside
    }  # fmt: skip
    if not budgets:
        raise CommandRejected("wrong_state", "This branch has no budget to raise")
    _nudge(engine, tx, cmd.investigation_id)
    return [_user("node.budget_changed", {"budget": budgets, "cause": "go_deeper"}, cmd.node_id)]


@handles("rerun_node")
async def _rerun_node(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Back to Pending with no verdict; its own claims are withdrawn (their sources stay, and
    pages and extractions are reused). Children are left as they are."""
    t = await _target(tx, cmd)
    node = t["node"]
    rt = engine.runtimes.get(cmd.investigation_id)
    if node["status"] not in ("Completed", "Failed") or (rt is not None and rt.busy(node["id"])):
        raise CommandRejected("wrong_state", "Only a finished node can be re-run")
    claims = await tx.fetchall(
        "SELECT id FROM claims WHERE node_id = ? AND withdrawn = 0 AND merged_into IS NULL",
        [node["id"]],
    )
    drafts = [_user("node.reset", {"reason": "rerun"}, node["id"])]
    if claims:
        drafts.append(_user("claim.withdrawn", {"claim_ids": [c["id"] for c in claims],
                                                "cause": "rerun"}, node["id"]))  # fmt: skip
    _nudge(engine, tx, cmd.investigation_id)
    return drafts


@handles("finish_now")
async def _finish_now(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """No new node starts; running steps finish; then Synthesising with `ended_early` for the
    report (S8). With nothing in flight it happens at once."""
    inv = cmd.investigation_id
    row = await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [inv])
    if row["state"] not in STEERABLE:
        raise CommandRejected("wrong_state", "Only running, paused or stopped research finishes")
    rt = engine.runtimes.get(inv)
    if row["state"] == "Running" and rt is not None and rt.active:
        tx.after_commit(rt.request_finish)
        return []
    from netgrip.engine.synthesis import synthesise

    tx.after_commit(lambda: engine.background(synthesise(engine, inv), f"finish:{inv}"))
    return finishing_events(row["state"])


def finishing_events(current: str) -> list[EventDraft]:
    return [
        EventDraft(type="investigation.concluding", actor="user",
                   data={"cut_short_by": None, "ended_early": True}),
        EventDraft(type="investigation.state_changed", actor="user",
                   data={"from": current, "to": "Synthesising", "origin": "user"}),
    ]  # fmt: skip


# --- Task 3: instructions ----------------------------------------------------------------------


@handles("add_instruction")
async def _add_instruction(engine: Engine, tx: Tx, cmd: Command) -> list[EventDraft]:
    """Queue an instruction for a node. It takes effect at the node's next step, never
    mid-step (E4), and applies to the node and everything below it (U1). The root cannot be
    instructed once research has started (Q-08)."""
    from netgrip.engine.instructions import apply_queued

    if cmd.node_id is None:
        raise CommandRejected("node_required", "This command needs a node")
    inv = cmd.investigation_id
    row = await tx.fetchone("SELECT state FROM investigations WHERE id = ?", [inv])
    node = await tx.fetchone(
        "SELECT id, display_id, parent_id, activity FROM nodes"
        " WHERE id = ? AND investigation_id = ?",
        [cmd.node_id, inv],
    )
    if node is None:
        raise CommandRejected("not_found", "No such node")
    if node["parent_id"] is None:
        raise CommandRejected("root_locked", "The root goal can not be instructed after approval")
    if row["state"] not in ("Running", "Paused"):
        raise CommandRejected("wrong_state", f"Not possible while {row['state']}")
    text = str(cmd.payload.get("text") or "").strip()
    if not text:
        raise CommandRejected("empty_instruction", "The instruction is empty")
    rt = engine.runtimes.get(inv)
    mid_step = rt is not None and rt.in_flight(node["id"])
    waiting_for = None
    if mid_step:
        what = (node["activity"] or "its step").upper()
        waiting_for = f"{node['display_id']} finishes {what}"
    else:
        nid = node["id"]
        tx.after_commit(
            lambda: engine.background(apply_queued(engine, inv, nid), f"instruction:{nid}")
        )
    return [
        EventDraft(
            type="instruction.queued", actor="user", node_id=node["id"],
            data={"instruction_id": str(uuid.uuid4()), "text": text, "waiting_for": waiting_for},
        )
    ]  # fmt: skip
