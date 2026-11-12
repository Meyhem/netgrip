# Phase 1: Backend foundation — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backend process that stores every change as an event, keeps state tables in step with it, accepts idempotent commands, and serves snapshots and a resumable live stream.

**Architecture:** One FastAPI process bound to loopback. The API layer talks to the engine only through `Engine.submit(command)` and `Engine.subscribe(...)` (D-02). The event log in SQLite is the source of truth; projections update state tables in the same transaction (D-06).

**Tech stack:** Python 3.12, uv, FastAPI, uvicorn, sse-starlette, aiosqlite, Pydantic v2, pytest, pytest-asyncio, ruff.

**Spec:** `docs/tech-spec-netgrip.md` sections 4–6, 8, 9; `docs/plans/00-overview.md` (event envelope, routes, default settings).

## Global constraints

- Bind to `127.0.0.1` only; any other host is refused at startup (C-04, section 8).
- SQLite in WAL mode, one writer path (section 5).
- One step's events and state changes commit in one transaction.
- Keys are write-only over the API and never appear in events or logs (D-13).
- Event shapes are versioned from the first release (R-05).
- Follow "Rules for every task" in the overview.

## Review focus

1. Two requests with the same command id arriving at the same moment: exactly one takes effect (Task 5).
2. A browser reconnecting with a sequence number higher than the log holds: the stream answers from the end, it does not error (Task 7).
3. A projector raising halfway through a batch: no event of that batch is stored (Task 4).
4. A prompt of 20,000 characters with newlines, quotes and emoji is stored and returned byte for byte (I1) (Task 5).
5. `PATCH /api/settings` with a negative or zero capacity is rejected with 422 and changes nothing (Task 6).

---

### Task 1: Project, config, health

**Files:** Create `backend/pyproject.toml`, `backend/src/netgrip/{__init__,__main__,app,config}.py`, `backend/tests/{conftest,test_app}.py`. Modify `.gitignore` (add `backend/.venv/`, `data/`).

**Interfaces — produces:**
- `Config(data_dir: Path, host: str = "127.0.0.1", port: int = 8321, fake: bool = False)`; `Config.from_env()` reads `NETGRIP_DATA_DIR` (default `~/netgrip/data`), `NETGRIP_PORT`, `NETGRIP_FAKE`.
- `create_app(config: Config) -> FastAPI`; script entry `netgrip = "netgrip.__main__:main"`.
- Fixture `app_client` (httpx `AsyncClient` over ASGI with a `tmp_path` data dir).

- [ ] Tests: `test_health` → `GET /api/health` is `200 {"status": "ok"}`; `test_refuses_non_loopback` → `Config(host="0.0.0.0")` makes `main()` exit with a message containing "loopback".
- [ ] Run `uv run pytest tests/test_app.py` — fails (no module).
- [ ] Implement; run — passes. `uv run ruff check` clean.
- [ ] Commit: `Add backend skeleton with health check`.

### Task 2: Database and migrations

**Files:** Create `store/db.py`, `store/migrations/0001_foundation.sql`, `tests/test_db.py`.

**Interfaces — produces:**
- `async open_db(path: Path) -> Database`; sets `journal_mode=WAL`, `foreign_keys=ON`, runs pending migrations.
- `Database.tx()` — async context manager; takes the writer lock, `BEGIN IMMEDIATE`, commits or rolls back. `Database.read(sql, params) -> list[Row]`.
- Migration 0001 tables: `schema_version`, `events(investigation_id, seq, type, v, at, actor, node_id, command_id, data, PRIMARY KEY(investigation_id, seq))`, `commands(id PRIMARY KEY, investigation_id, type, recorded_at)`, `investigations(id, prompt, state, pause_cause, pause_detail, settings, spending_limit_usd, spent_usd, spend_approximate, created_at, last_activity_at, last_seq)`, `settings(key PRIMARY KEY, value)`, `secrets(name PRIMARY KEY, value, status, checked_at, message)`.

- [ ] Tests: `test_wal_enabled`; `test_migrations_run_once` (open twice, version stays 1); `test_tx_rolls_back_on_error` (insert then raise → row absent).
- [ ] Fail, implement, pass.
- [ ] Commit: `Add SQLite store with migrations`.

### Task 3: Event model and log

**Files:** Create `boundary/events.py`, `store/eventlog.py`, `tests/test_eventlog.py`.

**Interfaces — produces:**
- `Event` (Pydantic; fields exactly as the overview's envelope), `EventDraft(type, actor, node_id=None, command_id=None, data={})`.
- `register_event(type: str, v: int, model: type[BaseModel])`; `register_upcaster(type, from_v, fn)`; Phase 1 registers `investigation.created` and `investigation.state_changed`.
- `async append(tx, investigation_id: str, drafts: list[EventDraft]) -> list[Event]`; `async read(db, investigation_id, after: int = 0, limit: int | None = None) -> list[Event]`.

- [ ] Tests: `test_seq_contiguous_from_one`; `test_seq_independent_per_investigation`; `test_unknown_type_rejected`; `test_data_validated_against_model`; `test_old_version_is_upcast_on_read` (store a `v: 0` row by hand, register an upcaster, read returns `v: 1` shape).
- [ ] Fail, implement, pass.
- [ ] Commit: `Add versioned append-only event log`.

### Task 4: Projections and rebuild

**Files:** Create `store/projections.py`, `store/rebuild.py`, `tests/test_projections.py`.

**Interfaces — produces:**
- `@projector("investigation.created")` decorator registering `async fn(tx, event)`.
- `async append_and_project(db, investigation_id, drafts) -> list[Event]` — one transaction: append, run projectors, set `investigations.last_seq`, then (after commit) publish to the bus (Task 5).
- `async rebuild(db, investigation_id: str | None = None) -> int` (events replayed); `async verify(db) -> list[str]` (ids whose `last_seq` differs from `max(seq)`).
- `STATE_TABLES: list[str]` — the tables a rebuild truncates. Later migrations append to it.

- [ ] Tests: `test_state_matches_event` (created → row with state `Draft`); `test_projector_error_stores_nothing`; `test_rebuild_reproduces_state` (dump state tables, rebuild, dumps are equal); `test_verify_detects_mismatch`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Project events into state tables and rebuild from the log`.

### Task 5: Commands, engine boundary, bus

**Files:** Create `boundary/commands.py`, `boundary/bus.py`, `engine/engine.py`, `tests/test_commands.py`.

**Interfaces — produces:**
- `Command(id: UUID, type: str, investigation_id: str, node_id: str | None, payload: dict)`; `CommandAck(recorded: bool, duplicate: bool)`; `CommandRejected(code: str, message: str)` (exception).
- `Ephemeral(investigation_id, node_id, kind, data)`.
- `EventBus.publish(item: Event | Ephemeral)`; `EventBus.subscribe(investigation_id) -> AsyncIterator`.
- `class Engine: __init__(db, config, bus)`, `async start()`, `async stop()`, `async submit(cmd: Command) -> CommandAck`, `async create_investigation(id: UUID, prompt: str, settings: dict) -> CommandAck`, `async delete_investigation(id: str)`, `subscribe(investigation_id: str, after_seq: int) -> AsyncIterator[Event | Ephemeral]`.
- `@handles("type")` decorator registering `async fn(engine, tx, cmd) -> list[EventDraft]`; the handler runs inside the command's transaction, raises `CommandRejected` when the command is not allowed, and returns the events it causes. Later phases add handlers without touching `submit`.

`submit` inserts into `commands` and appends the resulting events in one transaction; a primary-key conflict on `commands.id` means duplicate. `subscribe` reads the log after `after_seq`, then continues from the bus, dropping any event whose `seq` it has already yielded.

- [ ] Tests: `test_create_emits_created_and_is_draft`; `test_duplicate_id_is_noop`; `test_concurrent_duplicates_apply_once` (two `asyncio.gather` submits, one event); `test_unknown_command_rejected` (`code == "unknown_command"`); `test_prompt_kept_verbatim` (20,000 mixed characters); `test_subscribe_no_gap_no_duplicate` (subscribe from 0 while 200 events are appended concurrently; received seqs are `1..200`); `test_delete_removes_events_and_state`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add idempotent command boundary and event bus`.

### Task 6: Settings and keys

**Files:** Create `store/settings.py`, `tests/test_settings.py`.

**Interfaces — produces:**
- `DEFAULT_SETTINGS: dict` — exactly the overview's "Default settings" table, plus `presets` (`economy`, `balanced`, `maximum`; each maps `strong`, `standard`, `fast`, `verifier` to a model id), `default_preset: "balanced"`, `models` (list of `{id, price_in_per_m, price_out_per_m, price_source}`), `excluded_domains: []`.
- `SettingsModel` (Pydantic, all numeric limits `gt=0`); `async get_settings(db) -> SettingsModel`; `async patch_settings(db, partial: dict) -> SettingsModel`.
- `async set_key(db, name: Literal["model", "search"], value: str)`; `async get_key(db, name) -> str | None` (engine-internal only); `async key_status(db, name) -> KeyStatus(set: bool, status: Literal["none", "set", "rejected"], checked_at, message)`; `async mark_key(db, name, status, message)`.

- [ ] Tests: `test_defaults_match_overview` (Medium is depth 4, nodes 40, sources 8, parallel 4, confirm 2; limit `5.00`); `test_patch_persists`; `test_invalid_patch_rejected_and_unchanged`; `test_key_status_never_contains_value`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add settings store with write-only keys`.

### Task 7: HTTP API and live stream

**Files:** Create `api/{investigations,commands,stream,settings,system}.py`; modify `app.py`; create `tests/test_api.py`, `tests/test_stream.py`.

**Interfaces — produces** the Phase 1 routes of the overview. Shapes:
- List row: `{id, prompt, state, pause_cause, pause_detail, effort, nodes_total, nodes_max, running_count, spent_usd, spend_approximate, spending_limit_usd, disk_bytes, run_seconds, last_activity_at, summary}` (`summary` is filled by later phases; `null` now).
- Snapshot: `{seq, investigation: {…row, settings, root_goal}, nodes: [], instructions: [], premises: [], schedule: {order: [], reasons: {}, slots: 0}, focus_node_id: null, plan_version: 0}`.
- Stream: `event: durable`, `id: <seq>`, `data: <event json>`; `event: ephemeral` with no id. Start point is `Last-Event-ID` header, else `?after=`, else 0. A comment line every 15 s keeps the connection open.
- `GET /api/system/pools` → `{models: {in_use, limit}, search: {…}, browsers: {…}, today_usd}` (zeros in use until Phases 4 and 7). `GET /api/system/storage` → `{total_bytes, investigations, pages, data_dir}`.

- [ ] Tests: `test_create_then_list_then_snapshot`; `test_command_route_returns_202_and_duplicate_flag`; `test_rejected_command_is_409_with_code`; `test_settings_response_has_no_key_material` (set a key `sk-secret-123`, assert the string is absent from `GET /api/settings`, from `GET …/events` and from captured logs); `test_patch_settings_invalid_is_422`; `test_stream_resumes_after_seq` (read 3 events, reconnect with `Last-Event-ID: 3`, next id is 4); `test_stream_after_beyond_end_waits` (no error; next appended event arrives); `test_rebuild_route`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Serve queries, commands and the live stream`.

### Task 8: Serve the built frontend

**Files:** Modify `app.py`; create `tests/test_static.py`.

- [ ] Tests: with `frontend_dist` pointing at a temp folder holding `index.html`, `GET /` and `GET /investigations/abc` both return it (single-page fallback); `GET /api/nope` is 404 JSON, not the page.
- [ ] Implement `create_app(config, frontend_dist: Path | None = None)`; default `<repo>/frontend/dist` when it exists.
- [ ] Commit: `Serve the built frontend from the backend`.

---

## Phase verification

- [ ] `cd backend && uv run pytest` — all pass. `uv run ruff check` — clean.
- [ ] Start it: `NETGRIP_DATA_DIR=/tmp/ng1 uv run netgrip`. In another shell: create an investigation with `curl -X POST localhost:8321/api/investigations -H 'content-type: application/json' -d '{"id":"<uuid>","prompt":"test","settings":{}}'`; `curl localhost:8321/api/investigations` lists it as `Draft`; `curl -N localhost:8321/api/investigations/<id>/stream` prints event 1.
- [ ] Kill the process with `kill -9`, start it again, list again: the investigation is still there (N-03).
- [ ] `sqlite3 /tmp/ng1/netgrip.sqlite 'pragma journal_mode'` prints `wal`.
