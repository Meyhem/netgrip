"""The golden event contract shared with the frontend (Phase 3, Task 7).

Runs the fake Great Wall planning scenario (draft, one instruction, undo, another instruction,
approve) and writes its durable events and the final snapshot to `contract/plan_review.json`.
The frontend reduces those events from an empty snapshot and must reach the same snapshot.

Ids and timestamps are made deterministic (R12): `uuid.uuid4` and the event-log clock are
replaced by counters for the run. Regenerate with `NETGRIP_WRITE_GOLDEN=1 uv run pytest`.
"""

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from netgrip.adapters.fakes import FakeModelClient
from netgrip.api.investigations import snapshot
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import Command
from netgrip.config import Config
from netgrip.engine.engine import Engine
from netgrip.store import eventlog
from netgrip.store.db import open_db

GOLDEN = Path(__file__).resolve().parents[2] / "contract" / "plan_review.json"
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
        return {"events": events, "snapshot": await snapshot(inv, db)}
    finally:
        await engine.stop()
        await db.close()


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
    for t in ("investigation.created", "plan.version_created", "instruction.queued",
              "instruction.applied", "plan.reverted", "node.inclusion_changed",
              "node.approved", "spend.recorded"):  # fmt: skip
        assert t in types, t
