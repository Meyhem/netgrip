# Phase 5: Control board — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A running investigation is fully visible: what runs now, what comes next, what finished, the graph, the event log, and everything about one node.

**Architecture:** One screen, three panes over one store: ExecutionOrder (by time), GraphCanvas with the EventLog docked (by structure, by history), inspector (one node). A single selection is shared by all. The screen is read-only in this phase; controls arrive in Phase 6. The backend gains the node detail query and ephemeral model text.

**Tech stack:** as before.

**Spec:** design: ScreenControlBoard, ScreenNodeDetail, ExecutionOrder, EventLog, GraphNode, GraphCanvas, Verdict, ClaimCard, ClaimStatus, Brief, BudgetMeter READMEs and previews; `screens.md` (empty, loading and error states). Domain spec L1–L4, E1; tech spec section 6 (snapshot plus stream), D-11.

## Global constraints

- Three panes: left 284px, right 364px, header 60px, toolbar 40px.
- `live` appears only on running or waiting work; `steer` only on the user's marks and log rows. Selection is a 2px `ink` outline, never pink or cyan.
- The screen never guesses state; "current to #0419" shows the last applied sequence number.
- Streamed model text is shown but not stored; it disappears on reload (D-11).
- Page text is shown as inert text: no links followed, no scripts or images.
- Keys, prompts to models and page bodies never appear in the event log.
- One animation only (`ng-pulse`); it stops when paused, when the stream is disconnected and under `prefers-reduced-motion`.
- Follow "Rules for every task" in the overview.

## Review focus

1. Opening the board on a finished run with 80 nodes and 5,000 events: it opens from the snapshot; the log loads older rows on demand instead of all at once (Task 5).
2. The tab was closed for an hour of a run: on reopening, the log inserts "N events while this tab was closed" and the graph is correct (Task 5).
3. A node question of 400 characters: clamped to two lines on the node, full in the inspector, never rewritten (Task 3).
4. The selected node becomes Superseded by an event: it stays selected and the inspector shows the excluded Overview (Task 6).
5. A stored page containing `<script>` and `<img onerror>` text: rendered as characters, nothing executes (Task 7).

---

### Task 1: Node detail, page text and ephemeral model text (backend)

**Files:** Create `api/nodes.py`; extend `engine/steps.py` (stream `node.decide` and `aggregate` text), `store/projections.py` (trail table `node_steps`), migration `0004_trail.sql`; `tests/test_node_detail.py`.

**Interfaces — produces:**
- `GET /api/investigations/{id}/nodes/{node_id}` → `{node, brief, claims: [Claim with sources], trail: [{step, kind, activity, detail, started_at, ended_at, route, page_version_id, retry, instruction_applied: [instruction_id]}], instructions: {inherited: […with from_display_id], own: […]}, open_questions, proposals: [{node_id, display_id, question, decision, reason}], branch: {spent_usd, nodes, nodes_max, depth, depth_max, reach}}`.
- `GET /api/investigations/{id}/pages/{page_version_id}` → `{url, title, fetched_at, text}`; 404 unless the investigation used that version.
- Ephemeral message: `{"node_id", "kind": "model_text", "data": {"step": n, "delta": "…"}}` on the stream, no id, never written to the database.
- `GET /api/investigations/{id}/events` gains `before=` for paging backwards and `actor=`, `node_id=`, `types=` filters.
- Snapshot gains `recent_events` (the newest 200) so the log is filled without a second request.

- [ ] Tests: `test_node_detail_has_brief_as_received`; `test_trail_lists_steps_with_routes_and_retries`; `test_inherited_instructions_ordered_root_down`; `test_page_text_only_for_own_investigation`; `test_ephemeral_text_streamed_but_not_stored` (stream shows deltas; `events` table has none); `test_events_filter_and_page_backwards`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Serve node detail, stored pages and live model text`.

### Task 2: Selection, derived views and the board header

**Files:** Create `src/state/{selection.ts,derive.ts}`, `src/ui/BoardHeader.tsx`, `src/screens/ControlBoard.tsx` (layout only), tests.

**Interfaces — produces:**
- `useSelection(investigationId) → {selectedId, select(id | null)}` — one store; `null` means the root is shown in the inspector.
- `derive.ts` (pure): `sections(snapshot) → {now, next, done, notRunning}` per the ExecutionOrder table (Next ordered by `schedule.order`, each row with its wait reason; Done newest first); `counts(snapshot)`; `refutedPremises(snapshot)`; `reach(snapshot, nodeId) → number`; `waitReasonText(reason, nodes) → string` ("waits for D3 (dependency)", "waits for a free slot", "awaiting the orchestrator", "waits: you are running only D2", "paused").
- `<BoardHeader>`: back link; StatusPill with effort, preset, run time and running count; a `danger` pill "Premise refuted" when any is; the prompt as `title`; BudgetMeters Spend, Nodes, Depth; a slot for RunControls (Phase 6); overflow with "Export events" (downloads `/events` as JSON), "Open report", "Delete investigation". When the stream status is `reconnecting`, the pill gains "· reconnecting" in `warn`.

- [ ] Tests: `sections puts Paused, Ignored, Superseded and Rejected in notRunning`; `next follows schedule.order, not node order`; `refuted premise in done is flagged`; `header shows the danger pill when a premise is refuted`; `header pill shows "· reconnecting"`; `spend meter shows "≈" when approximate`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add board layout, shared selection and header`.

### Task 3: Execution order pane

**Files:** Create `src/ui/ExecutionOrder.tsx`, tests.

**Behaviour, from the ExecutionOrder README:** four sections always in the order Now, Next, Done, Not running, with sticky `ng-queue__head`; rows are `ng-qrow`. Now: ActivityLine and time in this run; head "4 running · 6 slots"; when Paused the section is empty and the head reads "Nothing runs while paused". Next: wait reason and position; when empty, "Nothing queued. The orchestrator is deciding." Done: verdict summary and confidence, or the failure reason; a refuted premise uses the `danger` cross. Not running: who excluded it; the Restore link is added in Phase 6. `↑ ↓` move the selection through the rows; selecting a row selects the node everywhere.

- [ ] Tests: `sections render in fixed order even when empty`; `paused head and empty Now`; `empty Next copy`; `refuted premise row uses the danger cross`; `arrow keys move selection`; `clicking a row calls select with the node id`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the execution order pane`.

### Task 4: Graph on the board

**Files:** Extend `src/ui/{GraphCanvas.tsx,GraphNode.tsx}`; create `src/ui/GraphToolbar.tsx`; tests.

**Behaviour:** `board` mode maps status to `ng-node--pending|running|waiting|paused|done|failed|rejected|proposed` and inclusion to `--excluded`; line 3 is the ActivityLine while Running, the verdict summary once Completed. Edges on the path from the root to a Running node are `ng-edge--live`. Toolbar: node counts in mono ("9 / 40 nodes · 4 running"), "current to #0419", and the toggles Fit, Collapse completed, Show excluded, Follow active (pans to the most recently started node). Folding a branch shows the hidden count ("+4"). When the selection changes from another pane, the canvas pans to the node. `← →` select the parent and the first child. Pulsing stops when the investigation is Paused or the stream is reconnecting (a class on the board root that the CSS already honours, or `animation: none` through the existing paused modifier in `bundle.css`).

- [ ] Tests: `running node has ng-node--running and an activity line`; `completed graph contains no live class`; `edges to a running node are ng-edge--live`; `Show excluded off hides excluded nodes; on shows them hatched`; `Collapse completed folds finished branches and shows the count`; `selection from outside pans the canvas` (transform changes); `left and right arrows move to parent and first child`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Show the running graph on the board`.

### Task 5: Event log

**Files:** Create `src/ui/EventLog.tsx`, `src/lib/eventText.ts`, tests.

**Interfaces — produces:**
- `eventText(ev, nodes) → {who: string, actorClass: "you"|"orc"|"sys"|"", text: string} | null` — verb first, then the object, then quoted text or numbers ("instructed D2", "approved D2c", "claim added", "completed", "paused: spending limit reached"). Returns `null` for events that are not log rows (`schedule.updated`, `spend.recorded`).
- `<EventLog events ephemeral selectedId onSelect collapsed onToggle>`.

**Behaviour, from the EventLog README:** newest first; one row per durable event with time, sequence number, who, what; actor modifiers `ng-log__row--you|--orc|--sys`; ephemeral model text as `ng-log__row--eph` with sequence "live". Head filters as tags: All, You, Orchestrator, Selected node, Claims, Problems, with counts when non-zero. "Follow" keeps the newest row in view; scrolling turns it off. Scrolling to the end loads older rows with `before=`. After a reconnect that brought more than 20 events at once, insert an `ng-log__gap` row "N events while this tab was closed". Clicking a row selects its node. `L` collapses the log to its head row.

- [ ] Tests: `eventText is verb-first for each event type` (table over the Phase 3–4 types); `user rows get ng-log__row--you`; `filters narrow rows and show counts`; `scrolling turns Follow off; the button turns it on`; `gap row appears after a large catch-up`; `older rows load on reaching the end`; `ephemeral rows vanish when the step completes`; `no row text contains a model prompt or page body` (fixture check).
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the event log`.

### Task 6: Inspector — header, Overview, Claims, Brief, Instructions

**Files:** Create `src/ui/{Inspector.tsx,Verdict.tsx,ClaimCard.tsx,ClaimStatus.tsx,Brief.tsx,Confidence.tsx}`, `src/state/useNodeDetail.ts`, tests.

**Interfaces — produces:**
- `useNodeDetail(investigationId, nodeId)` — fetches node detail; refetches when a durable event for that node (or a claim of it) arrives.
- `<Confidence level>` — `ng-conf` bars plus the word.
- `<Verdict verdict failed?>`, `<ClaimCard claim>` (status pill, text, supporting and contradicting sources with credibility; Weak sources dashed; unobtainable ones `ng-src--lost`), `<ClaimStatus status>`, `<Brief brief>`.

**Behaviour, from ScreenControlBoard region 4 and ScreenNodeDetail:** top: kind code, display id, depth, StatusPill, inclusion pill when not Included, question as `heading`, "Why" (justification), and a slot for NodeActions (Phase 6). Tabs (`ng-tabs`): Overview, Claims, Brief, Trail, Instructions. Overview by state: Running → Now block (ActivityLine, step number, time, sources read), claims so far, branch BudgetMeters, inherited instructions; Completed → Verdict first, then open questions and proposed follow-ups with the orchestrator's decision; Rejected → only the proposal, who proposed it and the reason; Ignored or Superseded → who excluded it and when, what is kept; Failed → Verdict in its failed state. Claims: filter tags by status, one ClaimCard per claim; empty copy "No claims yet. They appear here as pages are read." Instructions: inherited from the root down, then the node's own, oldest first (read-only Instruction blocks from Phase 3). With nothing selected the inspector shows the root. A composer slot is pinned at the bottom (filled in Phase 6).

- [ ] Tests: `nothing selected shows the root`; `overview per state` (five cases above); `claims empty copy`; `claim filter by status`; `weak source is dashed, unobtainable is ng-src--lost`; `brief shows root goal verbatim and the path`; `selected node turning Superseded keeps the selection and shows the excluded overview`; `confidence renders bars and the word`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the node inspector`.

### Task 7: Trail and stored page

**Files:** Create `src/ui/{Trail.tsx,PageSheet.tsx}`, tests.

**Behaviour:** one `ng-well` per step: step number, time, activity verb, detail, and "stored page" when the step has a `page_version_id`. The open step has a `live` border and shows streamed text in italic `ink-faint` with a caret, and under it the line "Live. This text is not stored." Retries are their own steps in `warn`, naming the route: simple fetch, full browser, hardened browser. A `steer` rule marks a step boundary where an instruction was applied. "stored page" opens `PageSheet`, a full-height sheet over the inspector, rendering the text in a `<pre>`-like block as a text node.

- [ ] Tests: `open step shows live text and the not-stored line`; `closed steps show only persisted detail`; `retry steps are warn and name the route`; `steer rule at the instruction boundary`; `page sheet renders "<script>alert(1)</script>" as text and creates no script or img element`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the trail and the stored page sheet`.

### Task 8: States, narrow widths, end-to-end

**Files:** Extend `ControlBoard.tsx`, `app.css`; `e2e/board.spec.ts`.

**Behaviour, from `screens.md`:** opening → header and empty panes with "Loading the investigation" as an ActivityLine, no shimmer. Synthesising → graph read-only, left pane "Writing the report from N claims". Completed or Stopped → the same board as history. Below 1180px the inspector is an overlay sheet over the graph; below 900px the left pane becomes a tab beside "Graph" and "Log".

- [ ] End-to-end, fake mode with a slowed scenario (`NETGRIP_FAKE_DELAY_MS=150`): approve the plan → Now fills, nodes turn `ng-node--running`, log rows arrive, "current to #" increases; click a node in the graph → the same node is highlighted in the left pane and shown in the inspector; open Trail → live text appears; open a stored page; reload mid-run → same state, no duplicated log rows; run ends → no element with a `live` class remains.
- [ ] End-to-end: block `/stream` with route interception → pill shows "· reconnecting" and pulsing stops; unblock → it clears and the log has no gap in sequence numbers.
- [ ] End-to-end at 1100×800 and 850×800: inspector is a sheet; left pane is a tab.
- [ ] Commit: `Finish board states and add end-to-end tests`.

---

## Phase verification

- [ ] `cd backend && uv run pytest`; `cd frontend && npm test && npx tsc --noEmit && npm run e2e` — all pass.
- [ ] Design check, dark and light: the board mid-run beside `ScreenControlBoard/preview.html` at 1440×970, and each inspector tab beside `ScreenNodeDetail/preview.html` at 1240×980. Pane widths 284 and 364. Pink only on node marks and user log rows; cyan only on running or waiting work.
- [ ] With the system set to reduce motion, no glyph pulses.
- [ ] By hand: open the board in two tabs; both show the same state within a second of each event (N-06).
