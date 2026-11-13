# Netgrip implementation plans: overview and shared contracts

The eight implementation phases are built and their per-phase plans are removed (they live in git history). This file stays as the reference for the shared contracts below: events, commands, routes, layout, default settings. Code comments cite it.

**Sources of truth.** `docs/domain-spec.md` (rules P1…R2), `docs/tech-spec-netgrip.md` (C-xx, D-xx, N-xx), `design-system/project/` (brand book `README.md`, `steering.md`, `screens.md`, one `README.md` + `preview.html` per component and screen). Where a plan and one of these disagree, the spec or design system wins; fix the plan.

## Rules for every task

- Test first: write the listed tests, see them fail, implement, see them pass.
- Finish each task with: run the relevant tests, `git add`, commit with the message the task gives, `git push origin main` (CLAUDE.md). Never commit the data directory, keys or fetched pages.
- Use the domain's words exactly, in code and in copy. State names are the strings in the tables below.
- Engine tests never touch the network (D-15). Live calls are manual.

## Build-time choices (mine; the tech spec defers them)

| Area | Choice | Why |
|---|---|---|
| Web framework | FastAPI + uvicorn, `sse-starlette` for the stream | async, small, typed |
| Data | `aiosqlite`, one connection, one writer lock; plain SQL migrations | D-06, D-14 |
| Models | Pydantic v2 for events, commands, API | versioned event shapes (R-05) |
| HTTP out | `httpx` | model client, Tavily, simple fetch |
| Browser | `playwright` (Chromium) | C-09 |
| Extraction | `trafilatura` behind the extractor interface | Crawl4AI manages its own browsers, which conflicts with the single owner rule in D-22 |
| Backend tests | `pytest`, `pytest-asyncio`, `ruff` | |
| Frontend | React 18, TypeScript, Vite, `react-router`, `zustand` | C-02 |
| Graph | `@dagrejs/dagre` for layout; nodes are DOM elements with `ng-node`, edges are SVG with `ng-edge` | a graph library would bring its own node styling; the design system already defines it |
| Frontend tests | `vitest`, `@testing-library/react`, Playwright for end-to-end | |

## Repository layout

```
backend/
  pyproject.toml
  src/netgrip/
    app.py  config.py  __main__.py
    boundary/   commands.py  events.py  bus.py
    store/      db.py  migrations/NNNN_*.sql  eventlog.py  projections.py  rebuild.py  settings.py  pages.py
    engine/     engine.py  runtime.py  scheduler.py  orchestrator.py  planner.py  agent.py  steps.py
                brief.py  budget.py  ids.py  limiter.py  recovery.py  synthesis.py  estimate.py  clock.py
    evidence/   service.py  status.py
    adapters/   model.py  model_openai.py  search.py  search_tavily.py  fetcher.py  fetch_http.py
                fetch_browser.py  browser_pool.py  extractor.py  fakes.py  fake_scenarios/*.json
    report/     model.py  markdown.py
    api/        investigations.py  commands.py  stream.py  nodes.py  report.py  settings.py  system.py
  tests/
contract/        golden event lists and the snapshots they produce; written by backend tests, read by frontend tests
frontend/
  src/
    api/      client.ts  types.ts  stream.ts
    state/    reduce.ts  investigationStore.ts  selection.ts
    ui/       one file per design-system component (Button.tsx, StatusPill.tsx, …)  vocab.ts
    screens/  Investigations.tsx  NewInvestigation.tsx  PlanReview.tsx  ControlBoard.tsx  Report.tsx  Settings.tsx
    lib/      format.ts  layout.ts  keys.ts  conclusionLike.ts
  e2e/
```

## Commands to run

| What | Command |
|---|---|
| Backend tests | `cd backend && uv run pytest` |
| Backend lint | `cd backend && uv run ruff check` |
| Backend, fake mode | `cd backend && NETGRIP_FAKE=1 NETGRIP_DATA_DIR=/tmp/netgrip-dev uv run netgrip` |
| Frontend unit tests | `cd frontend && npm test` |
| Frontend types | `cd frontend && npx tsc --noEmit` |
| End-to-end | `cd frontend && npm run e2e` (starts the backend in fake mode on a temporary data directory) |

`NETGRIP_FAKE=1` wires the fake model client, fake search and fake fetcher with the scripted scenario `great_wall` (the sample in the design previews). It exists so that every screen can be verified without keys or spend.

## Event envelope

Every durable event, in the database, on the stream and in `contract/`:

```json
{"seq": 419, "investigation_id": "…", "type": "node.completed", "v": 1,
 "at": "2026-11-12T19:04:11.201Z", "actor": "node", "node_id": "…",
 "command_id": null, "data": {}}
```

`seq` is contiguous from 1 per investigation. `actor` is `user`, `orchestrator`, `node` or `system`; the event log colours rows from it. `v` is the version of that type's `data` shape; a shape never changes in place, it gets a new `v` and an upcaster (R-05).

## Event types (all `v: 1`)

| Type | `data` | Introduced |
|---|---|---|
| `investigation.created` | `prompt`, `settings` | 1 |
| `investigation.state_changed` | `from`, `to`, `origin` (`user`/`system`/`orchestrator`), `cause`, `detail` | 1 |
| `investigation.root_goal_set` | `root_goal` | 3 |
| `premise.extracted` | `premise_id`, `text`, `node_id` | 3 |
| `premise.outcome` | `premise_id`, `outcome` (`confirmed`/`refuted`/`unverifiable`) | 4 |
| `plan.version_created` | `version`, `instruction_id`, `diff` | 3 |
| `plan.reverted` | `to_version`, `instruction_id` | 3 |
| `plan.failed` | `reason` | 3 |
| `plan.draft_requested` | none (the plan is being drafted, first time or again after `plan.failed`; clears the failure) | 3 |
| `node.proposed` | `display_id`, `parent_id`, `kind`, `question`, `justification`, `out_of_scope`, `done_when`, `depends_on`, `depth`, `proposed_by` | 3 |
| `node.approved` | `budget` (`sources`, `child_nodes`, optional `tier`: `verifier` for Verification nodes, used for their `node.decide` calls) | 3 |
| `node.rejected` | `reason`, `duplicate_of` | 4 |
| `node.started` | `attempt`, `brief` | 4 |
| `node.activity` | `activity`, `detail`, `step`, `retry` (`{n, m}` or null) | 4 |
| `node.step_completed` | `step`, `kind`, `summary`, `route`, `page_version_id` | 4 |
| `node.waiting_on_children` | none | 4 |
| `node.completed` | `verdict` (`text`, `confidence`), `open_questions`, `off_topic` (always false in v1; set later by `node.off_topic`) | 4 |
| `node.failed` | `reason`, `auto_retry_used` | 4 |
| `node.reset` | `reason` (`recovery`/`rerun`/`auto_retry`/`outage`: the node's step was interrupted by a provider error and the system paused; back to Pending), `hint` (optional: the different approach for an auto retry, shown in the brief) | 4 |
| `node.off_topic` | `reason` (the relevance gate found the result off-topic; its claims are kept out of synthesis, E3. A follow-up event so the node commits its own completion) | 4 |
| `node.relevance_checked` | `reason` (or null: no usable answer). The relevance gate kept a Completed node's result. With `node.off_topic` it is the durable record that the gate ran (`nodes.relevance_checked`); recovery redoes the gate for a Completed node without either | 4 |
| `node.left_failed` | `reason` (`auto_retry_used`/`spending_limit`): the orchestrator decided to leave a Failed node Failed. With `node.reset {reason: "auto_retry"}` it is the durable record that the failure was handled (`nodes.failure_handled`, cleared by `node.failed`); recovery redoes the decision otherwise | 4 |
| `node.paused`, `node.resumed` | `node_ids` | 6 |
| `node.inclusion_changed` | `node_ids`, `inclusion`, `by` (`user`/`replan`), `instruction_id` | 3 |
| `node.budget_changed` | `budget`, `cause` | 6 |
| `schedule.updated` | `order` (node ids in start order), `reasons` (node id → wait reason), `slots` | 4 |
| `focus.changed` | `node_id` or null | 6 |
| `instruction.queued` | `instruction_id`, `text`, `waiting_for` | 3 |
| `instruction.applied` | `instruction_id`, `at_step`, `diff` | 3 |
| `source.recorded` | `source_id`, `url`, `title`, `page_version_id`, `credibility`, `published_at`, `origin_key` | 4 |
| `page.unobtainable` | `url`, `attempts` | 4 |
| `claim.added` | `claim_id`, `text`, `status`, `supporting`, `contradicting` | 4 |
| `claim.updated` | `claim_id`, `status`, `supporting`, `contradicting`, `merged_into` (optional: the claim it was merged into) | 4 |
| `claim.contradiction_recorded` | `claim_ids` | 4 |
| `claim.withdrawn` | `claim_ids`, `cause` (`rerun`) | 6 |
| `spend.recorded` | `tier`, `model`, `amount_usd`, `approximate`, `tokens_in`, `tokens_out` | 3 |
| `limit.changed` | `spending_limit_usd` | 4 |
| `investigation.concluding` | `cut_short_by` (`budget` or null; the orchestrator decided to conclude, O3; feeds `report.created.cut_short_by`) | 4 |
| `system.recovered` | `reset_node_ids` (emitted at start, after its `node.reset {reason: "recovery"}` events, when an investigation had Running nodes (Running, Paused or Stopped investigations) or owed return work (Running); `reset_node_ids` may be empty when only return work is owed) | 4 |
| `report.created` | `report_id`, `ended_early`, `cut_short_by` | 8 |

`diff` is `{"kept": [node_id], "superseded": [node_id], "proposed": [node_id], "notes": [str]}`.

Wait reasons in `schedule.updated`: `dependency:<node_id>`, `slot`, `orchestrator`, `focus:<node_id>`, `paused`.

## State strings

- Investigation: `Draft`, `Planning`, `Running`, `Paused`, `Synthesising`, `Completed`, `Stopped`. The pill word for `Planning` is "Plan review".
- Node execution: `Proposed`, `Rejected`, `Pending`, `Running`, `Waiting on children`, `Paused`, `Completed`, `Failed`.
- Inclusion: `Included`, `Ignored`, `Superseded`.
- Kind → code: `Premise check` PRM, `Divergent` DIV, `Deep-dive` DEEP, `Verification` VER, `Synthesis` SYN.
- Claim status: `Confirmed`, `Supported`, `Unverified`, `Contested`, `Refuted`.
- Credibility: `Primary`, `Reputable`, `Weak`.
- Confidence: `low`, `medium`, `high` (shown as bars plus the word).
- Pause causes: `user`, `spending_limit`, `model_unavailable`, `search_unavailable`, `key_rejected`, `credit_exhausted`.
- Activities: `Planning`, `Searching`, `Reading`, `Extracting`, `Reasoning`, `Aggregating`, `Waiting on children`, `Retrying`.

## Commands

`POST /api/investigations/{id}/commands` with `{"id": "<uuid from the client>", "type": "…", "node_id": null, "payload": {}}`. Answers `202 {"recorded": true, "duplicate": false}`. A repeated `id` answers `duplicate: true` and does nothing. A command that is not allowed in the current state answers `409 {"code": "…", "message": "…"}`.

| Type | Level | Payload | Introduced |
|---|---|---|---|
| `draft_plan` | investigation | none | 3 |
| `instruct_plan` | investigation | `text` | 3 |
| `undo_plan_instruction` | investigation | none | 3 |
| `approve_plan` | investigation | none | 3 |
| `pause`, `resume`, `stop` | investigation | none | 4 |
| `raise_limit` | investigation | `spending_limit_usd` | 4 |
| `finish_now` | investigation | none | 6 (report in 8) |
| `ignore_branch`, `restore_branch` | node | none | 6 |
| `pause_branch`, `resume_branch` | node | none | 6 |
| `run_only_branch`, `run_everything` | node / investigation | none | 6 |
| `add_instruction` | node | `text` | 6 |
| `go_deeper` | node | none | 6 |
| `rerun_node` | node | none | 6 |

Creating is `POST /api/investigations` (same `id` rule); deleting is `DELETE /api/investigations/{id}`.

## Queries

| Route | Returns | Introduced |
|---|---|---|
| `GET /api/health` | `{"status": "ok"}` | 1 |
| `GET /api/investigations` | list rows | 1 |
| `GET /api/investigations/{id}` | snapshot, with the `seq` it is current to | 1 |
| `GET /api/investigations/{id}/events?after=&limit=` | durable events | 1 |
| `GET /api/investigations/{id}/stream?after=` | server-sent events: `event: durable` with `id: <seq>`, `event: ephemeral` without id | 1 |
| `GET /api/investigations/{id}/nodes/{node_id}` | brief, claims, trail, instructions | 5 |
| `GET /api/investigations/{id}/pages/{page_version_id}` | cleaned page text | 5 |
| `GET /api/investigations/{id}/report`, `/report.md` | structured report, Markdown | 8 |
| `GET/PATCH /api/settings` | non-secret settings | 1 |
| `PUT /api/settings/keys/{name}`, `POST …/check` | key status only, never the key | 1, 3 |
| `POST /api/estimate` | cost range per tier | 2 |
| `GET /api/system/pools`, `/storage`; `POST /api/system/rebuild` | pool use, disk, repair | 1 |

List rows (and the snapshot's `investigation`) carry derived fields, computed the same way by the backend (`summarise` in `api/investigations.py`) and the frontend reducer (`state/summary.ts`): `running_count` is the nodes `Running` while the investigation is Running; `nodes_total` the nodes below the root that were approved (not `Proposed` or `Rejected`); `summary` is, for Running, the first running node's activity (`"D1 Searching"`), for Paused, the cause (`"Reached the spending limit."`), then each refuted premise (`"Premise refuted: <text>"`), joined by ` · `, or null. The snapshot's `schedule` is the last `schedule.updated`; a node's `brief` is the object from its last `node.started`.

## Default settings (starting values, D-20; they match the Settings preview)

| Setting | Value |
|---|---|
| Effort Low | depth 2, nodes 12, sources per node 4, parallel 2, sources to confirm 1 |
| Effort Medium (default) | depth 4, nodes 40, sources per node 8, parallel 4, sources to confirm 2 |
| Effort High | depth 6, nodes 80, sources per node 12, parallel 6, sources to confirm 3 |
| Spending limit | `$5.00` |
| Retry before pausing | 5 minutes |
| Page reuse window | 1 day; other value `always_refetch` |
| Per-site politeness | 1 request every 2 seconds |
| Investigations in parallel | 5 |
| Model calls at once | 8 |
| Searches at once | 4 |
| Browser pages at once | 6 |
| Model endpoint | `https://openrouter.ai/api/v1` |

## How "stick to the design" is checked

1. **Class contract test** (`frontend/src/design.contract.test.ts`): every `ng-…` class used in `frontend/src` exists in `design-system/project/components/bundle.css`; `frontend/src` contains no colour literal (`#hex`, `rgb(`, `hsl(`) and no font-family literal. Colours and type come from `tokens.css` only.
2. **Vocabulary test** (`frontend/src/ui/vocab.test.ts`): the state → glyph, word, tone table equals the StatusPill and ClaimStatus READMEs.
3. **Screen check, per screen:** open the screen at the size in its preview's first line (`<!-- @dsCard … height=N page width=N -->`) beside `design-system/project/components/<Screen>/preview.html` and compare regions against the numbered list in the screen's README.
4. **No new visual components.** If a screen needs something the design system lacks, add it to the design system first (`design-system/build`), republish, then use it.

## Decisions I made that the specs leave open

- Display ids: root `R`; premise checks `P1…`; other children of the root `D1…`; verification nodes `V1…`; deeper levels alternate a letter and a number (`D2b`, `D2b1`); synthesis `S`.
- Confidence is `low`/`medium`/`high` (domain open question 6).
- The root cannot be instructed after approval (Q-08); the command answers `409 root_locked`.
- "Reads like a conclusion" is a local text heuristic in the browser, not a model call. It only changes the composer's foot; the instruction is still sent.
- Hardened browser means our own launch settings and init script; no third-party stealth package (D-12).
- **Not planned: "Ask a follow-up"** (domain I4, marked proposed). ScreenReport shows it as the steer button, but neither spec says how a follow-up changes the graph, the budget or the report. Until that is decided, the button is left out and "Export Markdown" is not promoted to steer. This is the one known departure from the design.
