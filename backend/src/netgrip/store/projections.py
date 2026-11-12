"""Projectors keep the state tables in step with the event log, in the same transaction (D-06)."""

import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Protocol

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
]

# Column holding the investigation id, for tables where it is not `investigation_id`.
ID_COLUMNS: dict[str, str] = {"investigations": "id"}


class Publisher(Protocol):
    def publish(self, item: Event) -> None: ...


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
    await tx.executemany(
        "UPDATE nodes SET inclusion = ?, updated_at = ? WHERE id = ?",
        [(event.data["inclusion"], event.at, nid) for nid in event.data["node_ids"]],
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
        "INSERT INTO instructions(id, investigation_id, node_id, text, state, queued_seq)"
        " VALUES (?, ?, ?, ?, 'queued', ?)",
        [event.data["instruction_id"], event.investigation_id, node_id, event.data["text"],
         event.seq],
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
