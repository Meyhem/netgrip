"""The golden event contracts shared with the frontend (Phase 3, Task 7; Phase 4, Task 9).

`contract/plan_review.json`: the fake Great Wall planning scenario (draft, one instruction,
undo, another instruction, approve): its durable events and the final snapshot.
`contract/run.json`: the fake Great Wall run from draft to Completed on the scripted web, one
node at a time (so the order is fixed): its durable events, a snapshot taken mid-run (P1
reading its second page) and the final snapshot.
The frontend reduces those events from an empty snapshot and must reach the same snapshots.

Ids and timestamps are made deterministic (R12): `uuid.uuid4` and the event-log clock are
replaced by counters for the run. Regenerate with `NETGRIP_WRITE_GOLDEN=1 uv run pytest`.
"""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from great_wall_run import MYTH, GatedFetcher, open_engine
from great_wall_run import run as great_wall_run

from netgrip.adapters.fakes import FakeModelClient
from netgrip.api.investigations import snapshot
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command
from netgrip.config import Config
from netgrip.engine.engine import Engine
from netgrip.store import eventlog
from netgrip.store.db import open_db

CONTRACT = Path(__file__).resolve().parents[2] / "contract"
GOLDEN = CONTRACT / "plan_review.json"
RUN_GOLDEN = CONTRACT / "run.json"
PROMPT = "Is the Great Wall visible from space?"
INVESTIGATION_ID = "00000000-0000-4000-8000-000000000000"


@pytest.fixture
def deterministic(monkeypatch):
    """Counter-based uuid4 and event clock, so the golden file is the same on every run."""
    counter = {"uuid": 0, "clock": 0}

    def fake_uuid4() -> uuid.UUID:
        counter["uuid"] += 1
        return uuid.UUID(f"00000000-0000-4000-8000-{counter['uuid']:012d}")

    start = datetime(2026, 1, 1, tzinfo=UTC)

    def fake_now() -> str:
        counter["clock"] += 1
        at = start + timedelta(seconds=counter["clock"])
        return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def reset() -> None:
        counter.update(uuid=0, clock=0)

    monkeypatch.setattr(uuid, "uuid4", fake_uuid4)
    monkeypatch.setattr(eventlog, "utc_now_iso", fake_now)
    return reset


async def run_scenario(path: Path) -> dict:
    path.mkdir(parents=True, exist_ok=True)
    db = await open_db(path / "golden.sqlite")
    engine = Engine(
        db,
        Config(data_dir=path, fake=True),
        EventBus(),
        FakeModelClient.from_scenario("great_wall"),
    )
    await engine.start()
    try:
        inv = INVESTIGATION_ID
        n = 0

        async def submit(type: str, **payload) -> None:
            nonlocal n
            n += 1
            command_id = uuid.UUID(f"00000000-0000-4000-9000-{n:012d}")
            await engine.submit(
                Command(id=command_id, type=type, investigation_id=inv, payload=payload)
            )
            await engine.planning.idle(inv)

        await engine.create_investigation(uuid.UUID(inv), PROMPT, {})
        await submit("draft_plan")
        await submit("instruct_plan", text="Drop the marketing angle; look at origins and photos.")
        await submit("undo_plan_instruction")
        await submit("instruct_plan", text="Add a check of astronaut accounts.")
        await submit("approve_plan")

        events = [e.model_dump(mode="json") for e in await eventlog.read(db, inv)]
        return {"events": events, "snapshot": await contract_snapshot(inv, db)}
    finally:
        await engine.stop()
        await db.close()


async def contract_snapshot(inv: str, db) -> dict:
    """The snapshot as the frontend reducer rebuilds it from events: without `recent_events`,
    the log's tail, which the event log keeps and the reducer does not (Phase 5)."""
    snap = await snapshot(inv, db)
    assert len(snap.pop("recent_events")) == min(200, snap["seq"])
    return snap


def dump(contract: dict) -> str:
    return json.dumps(contract, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


async def test_plan_review_contract_matches_the_golden_file(tmp_path, deterministic):
    text = dump(await run_scenario(tmp_path))
    if os.environ.get("NETGRIP_WRITE_GOLDEN") == "1":
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(text, encoding="utf-8")
    assert GOLDEN.exists(), "contract/plan_review.json is missing; run with NETGRIP_WRITE_GOLDEN=1"
    assert GOLDEN.read_text(encoding="utf-8") == text, (
        "the plan review contract changed; review it and regenerate with NETGRIP_WRITE_GOLDEN=1"
    )


async def test_the_scenario_is_deterministic_and_covers_plan_review(tmp_path, deterministic):
    first = await run_scenario(tmp_path / "a")
    deterministic()
    second = await run_scenario(tmp_path / "b")
    assert dump(first) == dump(second)
    assert first["snapshot"]["investigation"]["state"] == "Running"
    types = [e["type"] for e in first["events"]]
    for t in ("investigation.created", "plan.draft_requested", "plan.version_created",
              "instruction.queued", "instruction.applied", "plan.reverted",
              "node.inclusion_changed", "node.approved", "spend.recorded"):  # fmt: skip
        assert t in types, t


# --- The full run (Phase 4) --------------------------------------------------------------------

PHASE_4_TYPES = (
    "premise.outcome", "node.rejected", "node.started", "node.activity", "node.step_completed",
    "node.waiting_on_children", "node.completed", "node.failed", "node.reset", "node.off_topic",
    "node.relevance_checked", "node.left_failed", "schedule.updated", "source.recorded",
    "page.unobtainable", "claim.added", "claim.updated", "claim.contradiction_recorded",
    "limit.changed", "investigation.concluding", "system.recovered", "report.created",
)  # fmt: skip
# Types the scripted run reaches; the rest are covered by the frontend's reduce unit tests.
IN_THE_RUN = (
    "premise.outcome", "node.started", "node.activity", "node.step_completed",
    "node.waiting_on_children", "node.completed", "node.relevance_checked", "schedule.updated",
    "source.recorded", "claim.added", "investigation.concluding", "report.created",
    "node.proposed", "node.approved", "spend.recorded", "investigation.state_changed",
)  # fmt: skip


async def run_full(path: Path) -> dict:
    mid: list[dict] = []

    async def capture() -> None:  # the run is held inside P1's second read
        mid.append(await contract_snapshot(INVESTIGATION_ID, engine.db))

    engine = await open_engine(path, fetcher=GatedFetcher(MYTH, capture), parallel=1)
    try:
        n = 0

        def command_id() -> uuid.UUID:
            nonlocal n
            n += 1
            return uuid.UUID(f"00000000-0000-4000-9000-{n:012d}")

        r = great_wall_run(engine, INVESTIGATION_ID, command_id)
        await r.approved()
        await r.finished()
        events = [e.model_dump(mode="json") for e in await eventlog.read(engine.db, r.inv)]
        final = await contract_snapshot(r.inv, engine.db)
        return {"events": events, "snapshots": [*mid, final]}
    finally:
        await engine.stop()
        await engine.db.close()


async def test_run_contract_matches_the_golden_file(tmp_path, deterministic):
    text = dump(await run_full(tmp_path))
    if os.environ.get("NETGRIP_WRITE_GOLDEN") == "1":
        RUN_GOLDEN.write_text(text, encoding="utf-8")
    assert RUN_GOLDEN.exists(), "contract/run.json is missing; run with NETGRIP_WRITE_GOLDEN=1"
    assert RUN_GOLDEN.read_text(encoding="utf-8") == text, (
        "the run contract changed; review it and regenerate with NETGRIP_WRITE_GOLDEN=1"
    )


async def test_the_run_is_deterministic_and_reaches_completed(tmp_path, deterministic):
    first = await run_full(tmp_path / "a")
    deterministic()
    second = await run_full(tmp_path / "b")
    assert dump(first) == dump(second)
    mid, final = first["snapshots"]
    assert mid["investigation"]["state"] == "Running"
    assert mid["investigation"]["summary"] == "P1 Reading"
    assert final["investigation"]["state"] == "Completed"
    assert "Premise refuted" in final["investigation"]["summary"]
    types = {e["type"] for e in first["events"]}
    for t in IN_THE_RUN:
        assert t in types, t
    assert set(PHASE_4_TYPES) - types == {
        "node.rejected", "node.failed", "node.reset", "node.off_topic", "node.left_failed",
        "page.unobtainable", "claim.updated", "claim.contradiction_recorded", "limit.changed",
        "system.recovered",
    }  # fmt: skip
