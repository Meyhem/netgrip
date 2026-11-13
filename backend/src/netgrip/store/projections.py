"""Projectors keep the state tables in step with the event log, in the same transaction (D-06)."""

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Protocol

from netgrip.adapters.fetcher import ROUTES
from netgrip.boundary.bus import Ephemeral
from netgrip.boundary.events import Event, EventDraft
from netgrip.store import eventlog
from netgrip.store.db import Database, Tx

Projector = Callable[[Tx, Event], Awaitable[None]]

_projectors: dict[str, list[Projector]] = defaultdict(list)

# Tables a rebuild truncates and refills from the log. Later migrations append to this list.
STATE_TABLES: list[str] = [
    "investigations",
    "nodes",
    "node_deps",
    "instructions",
    "premises",
    "plan_versions",
    "sources",
    "claims",
    "claim_sources",
    "contradictions",
    "node_steps",
    "reports",
]

# Column holding the investigation id, for tables where it is not `investigation_id`.
ID_COLUMNS: dict[str, str] = {"investigations": "id"}


class Publisher(Protocol):
    def publish(self, item: Event | Ephemeral) -> None: ...


def projector(type: str) -> Callable[[Projector], Projector]:
    def register(fn: Projector) -> Projector:
        _projectors[type].append(fn)
        return fn

    return register


async def project(tx: Tx, events: list[Event]) -> None:
    """Run every projector for `events`, then stamp the investigation row."""
    for event in events:
        for fn in _projectors.get(event.type, ()):
            await fn(tx, event)
    if events:
        last = events[-1]
        await tx.execute(
            "UPDATE investigations SET last_seq = ?, last_activity_at = ? WHERE id = ?",
            [last.seq, last.at, last.investigation_id],
        )


async def append_and_project_in_tx(
    tx: Tx, investigation_id: str, drafts: list[EventDraft], bus: Publisher | None = None
) -> list[Event]:
    events = await eventlog.append(tx, investigation_id, drafts)
    await project(tx, events)
    if bus is not None:

        def _publish() -> None:
            for e in events:
                bus.publish(e)

        tx.after_commit(_publish)
    return events


async def append_and_project(
    db: Database, investigation_id: str, drafts: list[EventDraft], bus: Publisher | None = None
) -> list[Event]:
    async with db.tx() as tx:
        return await append_and_project_in_tx(tx, investigation_id, drafts, bus)


# --- Phase 1 projectors ----------------------------------------------------------------------


@projector("investigation.created")
async def _created(tx: Tx, event: Event) -> None:
    settings = event.data["settings"]
    await tx.execute(
        "INSERT INTO investigations(id, prompt, state, settings, spending_limit_usd,"
        " created_at, last_activity_at) VALUES (?, ?, 'Draft', ?, ?, ?, ?)",
        [
            event.investigation_id,
            event.data["prompt"],
            json.dumps(settings, ensure_ascii=False),
            float(settings.get("spending_limit_usd", 5.0)),
            event.at,
            event.at,
        ],
    )


@projector("investigation.state_changed")
async def _state_changed(tx: Tx, event: Event) -> None:
    paused = event.data["to"] == "Paused"
    await tx.execute(
        "UPDATE investigations SET state = ?, pause_cause = ?, pause_detail = ? WHERE id = ?",
        [
            event.data["to"],
            event.data.get("cause") if paused else None,
            event.data.get("detail") if paused else None,
            event.investigation_id,
        ],
    )


@projector("spend.recorded")
async def _spend_recorded(tx: Tx, event: Event) -> None:
    amount = float(Decimal(event.data["amount_usd"]))
    await tx.execute(
        "UPDATE investigations SET spent_usd = spent_usd + ?,"
        " spend_approximate = MAX(spend_approximate, ?) WHERE id = ?",
        [amount, int(event.data["approximate"]), event.investigation_id],
    )
    if event.node_id:
        await tx.execute(
            "UPDATE nodes SET spent_usd = spent_usd + ? WHERE id = ?", [amount, event.node_id]
        )


# --- Phase 3 projectors: graph, instructions, premises ---------------------------------------


def _j(value: object) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False)


@projector("investigation.root_goal_set")
async def _root_goal_set(tx: Tx, event: Event) -> None:
    row = await tx.fetchone(
        "SELECT root_goal FROM investigations WHERE id = ?", [event.investigation_id]
    )
    if row is not None and row["root_goal"] is not None:
        raise ValueError("root goal is already set (I1)")
    await tx.execute(
        "UPDATE investigations SET root_goal = ? WHERE id = ?",
        [event.data["root_goal"], event.investigation_id],
    )


@projector("premise.extracted")
async def _premise_extracted(tx: Tx, event: Event) -> None:
    await tx.execute(
        "INSERT INTO premises(id, investigation_id, text, node_id, seq) VALUES (?, ?, ?, ?, ?)",
        [
            event.data["premise_id"],
            event.investigation_id,
            event.data["text"],
            event.data.get("node_id"),
            event.seq,
        ],
    )


@projector("node.proposed")
async def _node_proposed(tx: Tx, event: Event) -> None:
    d = event.data
    # Provisional plan_version_added: the version this node will land in. plan.version_created
    # confirms it for the nodes in its diff, so the value is the same on rebuild.
    row = await tx.fetchone(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM plan_versions WHERE investigation_id = ?",
        [event.investigation_id],
    )
    await tx.execute(
        "INSERT INTO nodes(id, investigation_id, display_id, parent_id, kind, question,"
        " justification, out_of_scope, done_when, depth, plan_version_added, proposed_by,"
        " created_at, updated_at, seq) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            event.node_id,
            event.investigation_id,
            d["display_id"],
            d.get("parent_id"),
            d["kind"],
            d["question"],
            d.get("justification"),
            _j(d.get("out_of_scope")),
            _j(d.get("done_when")),
            d.get("depth", 0),
            row[0] if row else 1,
            d.get("proposed_by"),
            event.at,
            event.at,
            event.seq,
        ],
    )
    await tx.executemany(
        "INSERT INTO node_deps(investigation_id, node_id, depends_on_id) VALUES (?, ?, ?)",
        [(event.investigation_id, event.node_id, dep) for dep in d.get("depends_on", [])],
    )


@projector("node.approved")
async def _node_approved(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE nodes SET status = 'Pending', budget = ?, updated_at = ? WHERE id = ?",
        [_j(event.data["budget"]), event.at, event.node_id],
    )


@projector("node.inclusion_changed")
async def _inclusion_changed(tx: Tx, event: Event) -> None:
    # Who excluded it and when; a restore (Included) clears both.
    d = event.data
    included = d["inclusion"] == "Included"
    await tx.executemany(
        "UPDATE nodes SET inclusion = ?, excluded_by = ?, excluded_at = ?,"
        " excluded_instruction_id = ?, updated_at = ? WHERE id = ?",
        [
            (
                d["inclusion"],
                None if included else d["by"],
                None if included else event.at,
                None if included else d.get("instruction_id"),
                event.at,
                nid,
            )
            for nid in d["node_ids"]
        ],
    )


@projector("instruction.queued")
async def _instruction_queued(tx: Tx, event: Event) -> None:
    node_id = event.node_id
    if node_id is None:
        root = await tx.fetchone(
            "SELECT id FROM nodes WHERE investigation_id = ? AND parent_id IS NULL"
            " ORDER BY seq LIMIT 1",
            [event.investigation_id],
        )
        node_id = root["id"] if root else None
    await tx.execute(
        "INSERT INTO instructions(id, investigation_id, node_id, text, state, queued_seq,"
        " waiting_for) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
        [event.data["instruction_id"], event.investigation_id, node_id, event.data["text"],
         event.seq, event.data.get("waiting_for")],
    )  # fmt: skip


@projector("instruction.applied")
async def _instruction_applied(tx: Tx, event: Event) -> None:
    iid = event.data["instruction_id"]
    await tx.execute(
        "UPDATE instructions SET state = 'applied', applied_seq = ?, diff = ? WHERE id = ?",
        [event.seq, _j(event.data["diff"]), iid],
    )
    await tx.execute(
        "UPDATE nodes SET instruction_count = instruction_count + 1 WHERE id ="
        " (SELECT node_id FROM instructions WHERE id = ?)",
        [iid],
    )


@projector("plan.version_created")
async def _plan_version_created(tx: Tx, event: Event) -> None:
    d = event.data
    # After an undo the next version reuses the number of the undone one (R7); plan.reverted
    # deleted that row.
    await tx.execute(
        "INSERT INTO plan_versions(investigation_id, version, instruction_id, diff)"
        " VALUES (?, ?, ?, ?)",
        [event.investigation_id, d["version"], d.get("instruction_id"), _j(d["diff"])],
    )
    await tx.executemany(
        "UPDATE nodes SET plan_version_added = ? WHERE id = ?",
        [(d["version"], nid) for nid in d["diff"].get("proposed", [])],
    )
    await tx.execute(
        "UPDATE investigations SET plan_failed_reason = NULL WHERE id = ?",
        [event.investigation_id],
    )


@projector("plan.reverted")
async def _plan_reverted(tx: Tx, event: Event) -> None:
    # The current version is the highest left, so the versions above `to_version` go.
    await tx.execute(
        "DELETE FROM plan_versions WHERE investigation_id = ? AND version > ?",
        [event.investigation_id, event.data["to_version"]],
    )
    await tx.execute(
        "UPDATE instructions SET state = 'undone', undone = 1 WHERE id = ?",
        [event.data["instruction_id"]],
    )


@projector("plan.failed")
async def _plan_failed(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE investigations SET plan_failed_reason = ? WHERE id = ?",
        [event.data["reason"], event.investigation_id],
    )


@projector("plan.draft_requested")
async def _plan_draft_requested(tx: Tx, event: Event) -> None:
    # A new draft is under way: the last failure no longer stands.
    await tx.execute(
        "UPDATE investigations SET plan_failed_reason = NULL WHERE id = ?",
        [event.investigation_id],
    )


# --- Phase 4 projectors: evidence -------------------------------------------------------------


@projector("source.recorded")
async def _source_recorded(tx: Tx, event: Event) -> None:
    d = event.data
    await tx.execute(
        "INSERT INTO sources(id, investigation_id, url, title, page_version_id, credibility,"
        " published_at, origin_key, seq) VALUES (?,?,?,?,?,?,?,?,?)",
        [d["source_id"], event.investigation_id, d["url"], d.get("title"), d["page_version_id"],
         d["credibility"], d.get("published_at"), d["origin_key"], event.seq],
    )  # fmt: skip


async def _set_claim_sources(tx: Tx, event: Event) -> None:
    d = event.data
    await tx.execute("DELETE FROM claim_sources WHERE claim_id = ?", [d["claim_id"]])
    rows = [(event.investigation_id, d["claim_id"], s, "supports") for s in d["supporting"]]
    rows += [(event.investigation_id, d["claim_id"], s, "contradicts") for s in d["contradicting"]]
    await tx.executemany(
        "INSERT OR REPLACE INTO claim_sources(investigation_id, claim_id, source_id, stance)"
        " VALUES (?,?,?,?)",
        rows,
    )


@projector("claim.added")
async def _claim_added(tx: Tx, event: Event) -> None:
    d = event.data
    await tx.execute(
        "INSERT INTO claims(id, investigation_id, node_id, text, status, seq) VALUES (?,?,?,?,?,?)",
        [d["claim_id"], event.investigation_id, event.node_id, d["text"], d["status"], event.seq],
    )
    await _set_claim_sources(tx, event)


@projector("claim.updated")
async def _claim_updated(tx: Tx, event: Event) -> None:
    d = event.data
    await tx.execute(
        "UPDATE claims SET status = ?, merged_into = COALESCE(?, merged_into) WHERE id = ?",
        [d["status"], d.get("merged_into"), d["claim_id"]],
    )
    await _set_claim_sources(tx, event)


@projector("claim.contradiction_recorded")
async def _claim_contradiction(tx: Tx, event: Event) -> None:
    a, b = sorted(event.data["claim_ids"])
    await tx.execute(
        "INSERT OR IGNORE INTO contradictions(investigation_id, claim_a, claim_b) VALUES (?,?,?)",
        [event.investigation_id, a, b],
    )


@projector("premise.outcome")
async def _premise_outcome(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE premises SET outcome = ? WHERE id = ?",
        [event.data["outcome"], event.data["premise_id"]],
    )


# --- Phase 4 projectors: the node agent loop --------------------------------------------------


async def _node_status(tx: Tx, event: Event, status: str, activity: str | None) -> None:
    await tx.execute(
        "UPDATE nodes SET status = ?, activity = ?, updated_at = ? WHERE id = ?",
        [status, activity, event.at, event.node_id],
    )


@projector("node.started")
async def _node_started(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE nodes SET status = 'Running', activity = NULL, verdict = NULL, brief = ?,"
        " finished_seq = NULL, finished_at = NULL, failure_reason = NULL,"
        " off_topic = 0, relevance_checked = 0, updated_at = ? WHERE id = ?",
        [_j(event.data["brief"]), event.at, event.node_id],
    )


@projector("node.activity")
async def _node_activity(tx: Tx, event: Event) -> None:
    # The status is left alone: a node aggregating stays `Waiting on children` until it
    # completes, so after a restart it is still recognised as a coordinator (Task 8).
    # A node reset by an outage and continued from its kept context shows Running again.
    await tx.execute(
        "UPDATE nodes SET activity = ?, updated_at = ?,"
        " status = CASE WHEN status = 'Pending' THEN 'Running' ELSE status END WHERE id = ?",
        [event.data["activity"], event.at, event.node_id],
    )


@projector("node.waiting_on_children")
async def _node_waiting(tx: Tx, event: Event) -> None:
    await _node_status(tx, event, "Waiting on children", "Waiting on children")


@projector("node.completed")
async def _node_completed(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE nodes SET status = 'Completed', activity = NULL, verdict = ?, off_topic = ?,"
        " finished_seq = ?, finished_at = ?, failure_reason = NULL, updated_at = ? WHERE id = ?",
        [
            _j(event.data["verdict"]),
            int(event.data.get("off_topic", False)),
            event.seq,
            event.at,
            event.at,
            event.node_id,
        ],  # fmt: skip
    )


@projector("node.failed")
async def _node_failed(tx: Tx, event: Event) -> None:
    await _node_status(tx, event, "Failed", None)
    await tx.execute(
        "UPDATE nodes SET failure_handled = 0, finished_seq = ?, finished_at = ?,"
        " failure_reason = ? WHERE id = ?",
        [event.seq, event.at, event.data["reason"], event.node_id],
    )


@projector("node.left_failed")
async def _node_left_failed(tx: Tx, event: Event) -> None:
    await tx.execute("UPDATE nodes SET failure_handled = 1 WHERE id = ?", [event.node_id])


@projector("node.reset")
async def _node_reset(tx: Tx, event: Event) -> None:
    await _node_status(tx, event, "Pending", None)
    await tx.execute(
        "UPDATE nodes SET finished_seq = NULL, finished_at = NULL, failure_reason = NULL"
        " WHERE id = ?",
        [event.node_id],
    )
    if event.data["reason"] == "rerun":
        await tx.execute("UPDATE nodes SET verdict = NULL WHERE id = ?", [event.node_id])
    # An auto retry carries its hint; a recovery, outage or steering stop keeps it (same
    # attempt); a user rerun clears it.
    if event.data["reason"] not in ("recovery", "outage", "ignored", "focus"):
        await tx.execute(
            "UPDATE nodes SET retry_hint = ? WHERE id = ?", [event.data.get("hint"), event.node_id]
        )


@projector("node.rejected")
async def _node_rejected(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE nodes SET status = 'Rejected', rejection_reason = ?, duplicate_of = ?,"
        " updated_at = ? WHERE id = ?",
        [event.data["reason"], event.data.get("duplicate_of"), event.at, event.node_id],
    )


@projector("node.off_topic")
async def _node_off_topic(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE nodes SET off_topic = 1, relevance_checked = 1, updated_at = ? WHERE id = ?",
        [event.at, event.node_id],
    )


@projector("node.relevance_checked")
async def _node_relevance_checked(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE nodes SET relevance_checked = 1, updated_at = ? WHERE id = ?",
        [event.at, event.node_id],
    )


@projector("investigation.concluding")
async def _concluding(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE investigations SET cut_short_by = ?, ended_early = ? WHERE id = ?",
        [
            event.data.get("cut_short_by"),
            int(event.data.get("ended_early", False)),
            event.investigation_id,
        ],
    )


@projector("report.created")
async def _report_created(tx: Tx, event: Event) -> None:
    """One report per investigation: a new synthesis replaces the old one."""
    body = event.data.get("body")
    if body is None:
        return
    await tx.execute("DELETE FROM reports WHERE investigation_id = ?", [event.investigation_id])
    await tx.execute(
        "INSERT INTO reports(id, investigation_id, created_at, body) VALUES (?, ?, ?, ?)",
        [event.data["report_id"], event.investigation_id, event.at, json.dumps(body)],
    )


@projector("limit.changed")
async def _limit_changed(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE investigations SET spending_limit_usd = ? WHERE id = ?",
        [float(event.data["spending_limit_usd"]), event.investigation_id],
    )


# --- Phase 5 projectors: the trail (node_steps) ----------------------------------------------


async def _last_step(tx: Tx, node_id: str | None):
    return await tx.fetchone(
        "SELECT step, ended_at, instruction_applied FROM node_steps WHERE node_id = ?"
        " ORDER BY step DESC LIMIT 1",
        [node_id],
    )


async def _close_step(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE node_steps SET ended_at = ? WHERE node_id = ? AND ended_at IS NULL",
        [event.at, event.node_id],
    )


@projector("node.activity")
async def _trail_activity(tx: Tx, event: Event) -> None:
    """Each activity opens a step; a retry is its own step (a fetch retry on the route it
    tries)."""
    d = event.data
    await _close_step(tx, event)
    last = await _last_step(tx, event.node_id)
    retry = d.get("retry")
    route = None
    # Only a read's retries are fetch retries: the fetcher tries the routes in turn. A retry
    # after a model or search outage (the runtime's) has no route.
    if retry and d["step"] == "read" and 1 <= retry["n"] <= len(ROUTES):
        route = ROUTES[retry["n"] - 1]
    await tx.execute(
        "INSERT INTO node_steps(investigation_id, node_id, step, name, activity, detail,"
        " started_at, route, retry, instruction_applied) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [event.investigation_id, event.node_id, (last["step"] if last else 0) + 1, d["step"],
         d["activity"], d.get("detail"), event.at, route, _j(retry),
         json.dumps([] if last else await _applied_to(tx, event.node_id))],
    )  # fmt: skip


@projector("node.step_completed")
async def _trail_step_completed(tx: Tx, event: Event) -> None:
    """Closes the open step with its result; a step that had no activity (propose, conclude)
    gets a row of its own."""
    d = event.data
    last = await _last_step(tx, event.node_id)
    if last is None or last["ended_at"] is not None:
        step = (last["step"] if last else 0) + 1
        await tx.execute(
            "INSERT INTO node_steps(investigation_id, node_id, step, name, started_at,"
            " instruction_applied) VALUES (?,?,?,?,?,?)",
            [
                event.investigation_id,
                event.node_id,
                step,
                d["step"],
                event.at,
                json.dumps([] if last else await _applied_to(tx, event.node_id)),
            ],
        )
    else:
        step = last["step"]
    await tx.execute(
        "UPDATE node_steps SET kind = ?, summary = ?, ended_at = ?,"
        " route = COALESCE(?, route), page_version_id = ? WHERE node_id = ? AND step = ?",
        [d["kind"], d["summary"], event.at, d.get("route"), d.get("page_version_id"),
         event.node_id, step],
    )  # fmt: skip


for _type in ("node.started", "node.waiting_on_children", "node.completed", "node.failed",
              "node.reset"):  # fmt: skip
    projector(_type)(_close_step)


async def _applied_to(tx: Tx, node_id: str) -> list[str]:
    rows = await tx.fetchall(
        "SELECT id FROM instructions WHERE node_id = ? AND state = 'applied' ORDER BY applied_seq",
        [node_id],
    )
    return [r["id"] for r in rows]


async def _mark_boundary(tx: Tx, node_id: str, instruction_id: str) -> None:
    last = await _last_step(tx, node_id)
    if last is None:
        return  # no step yet: its first step picks the instruction up (`_applied_to`)
    applied = json.loads(last["instruction_applied"])
    if instruction_id in applied:
        return
    await tx.execute(
        "UPDATE node_steps SET instruction_applied = ? WHERE node_id = ? AND step = ?",
        [json.dumps([*applied, instruction_id]), node_id, last["step"]],
    )


@projector("instruction.applied")
async def _trail_instruction(tx: Tx, event: Event) -> None:
    """Marks the boundary after the latest step of the instruction's node and of every node
    below it that is running: the step in flight finishes first, so the instruction takes
    effect after it (U1, E4)."""
    iid = event.data["instruction_id"]
    row = await tx.fetchone("SELECT node_id FROM instructions WHERE id = ?", [iid])
    if not row or not row["node_id"]:
        return
    await _mark_boundary(tx, row["node_id"], iid)
    below = await tx.fetchall(
        "WITH RECURSIVE sub(id) AS (SELECT id FROM nodes WHERE parent_id = ?"
        " UNION SELECT n.id FROM nodes n JOIN sub ON n.parent_id = sub.id)"
        " SELECT n.id FROM nodes n JOIN sub ON n.id = sub.id WHERE n.status = 'Running'",
        [row["node_id"]],
    )
    for n in below:
        await _mark_boundary(tx, n["id"], iid)


# --- Phase 6 projectors: steering ------------------------------------------------------------

PAUSABLE = ("Pending", "Running", "Waiting on children")


@projector("node.paused")
async def _node_paused(tx: Tx, event: Event) -> None:
    """Pending, Running and Waiting nodes become Paused (remembering which); others are left."""
    for nid in event.data["node_ids"]:
        await tx.execute(
            "UPDATE nodes SET paused_from = status, status = 'Paused', updated_at = ?"
            f" WHERE id = ? AND status IN ({','.join('?' * len(PAUSABLE))})",
            [event.at, nid, *PAUSABLE],
        )


@projector("node.resumed")
async def _node_resumed(tx: Tx, event: Event) -> None:
    """Back to Waiting on children if that is what was interrupted, else to Pending (a node
    that was running continues from its kept context)."""
    for nid in event.data["node_ids"]:
        await tx.execute(
            "UPDATE nodes SET status = CASE WHEN paused_from = 'Waiting on children'"
            " THEN 'Waiting on children' ELSE 'Pending' END, paused_from = NULL, updated_at = ?"
            " WHERE id = ? AND status = 'Paused'",
            [event.at, nid],
        )


@projector("focus.changed")
async def _focus_changed(tx: Tx, event: Event) -> None:
    await tx.execute(
        "UPDATE investigations SET focus_node_id = ? WHERE id = ?",
        [event.data.get("node_id"), event.investigation_id],
    )


@projector("node.budget_changed")
async def _node_budget_changed(tx: Tx, event: Event) -> None:
    """New budgets replace the old; the investigation's node ceiling rises by the added child
    nodes."""
    added = 0
    for nid, budget in event.data["budget"].items():
        row = await tx.fetchone("SELECT budget FROM nodes WHERE id = ?", [nid])
        if row is None:
            continue
        old = json.loads(row["budget"] or "{}")
        added += max(0, int(budget.get("child_nodes", 0)) - int(old.get("child_nodes", 0)))
        await tx.execute(
            "UPDATE nodes SET budget = ?, updated_at = ? WHERE id = ?",
            [_j(budget), event.at, nid],
        )
    await tx.execute(
        "UPDATE investigations SET nodes_extra = nodes_extra + ? WHERE id = ?",
        [added, event.investigation_id],
    )


@projector("claim.withdrawn")
async def _claim_withdrawn(tx: Tx, event: Event) -> None:
    await tx.executemany(
        "UPDATE claims SET withdrawn = 1 WHERE id = ?", [(c,) for c in event.data["claim_ids"]]
    )
