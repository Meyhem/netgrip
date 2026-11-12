# Phase 3: Planning and plan review — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** "Draft the plan" turns a prompt into a root goal, premises and a first graph; the user reshapes it with instructions, sees each change arrive live, and approves it.

**Architecture:** Planning is a phase of the normal lifecycle (D-17): the planner emits the same `node.proposed` events the running engine will use. The model client interface arrives here with an OpenAI-compatible implementation and a scripted fake. The frontend gains the live stream store, the graph canvas and the instruction composer.

**Tech stack:** as Phases 1–2, plus httpx (model calls), `@dagrejs/dagre`.

**Spec:** domain spec 4.9 (plan review, re-planning), I1, I2, I5, G1, G4, U1–U6, B5; tech spec section 6 "Plan review", D-04, D-17, A-08, R-01; design: ScreenPlanReview, GraphCanvas, GraphNode, InstructionComposer, Instruction, `steering.md`.

## Global constraints

- No web research during planning (A-08): the planner has no search or fetch tool.
- Planning spend counts towards the spending limit (B5).
- Premise checks can never be removed by an instruction; they run first (I2).
- The prompt and root goal never change after they are set (I1).
- The frontend applies events; it never invents state. Controls show `is-sent` wording until the confirming event arrives.
- On ScreenPlanReview the only steer button is "Approve plan and start"; the composer's button is the neutral "Re-plan".
- Follow "Rules for every task" in the overview.

## Review focus

1. The model returns a plan with a dependency cycle or a node without justification: the plan is rejected and retried, never shown (G1, G4) (Task 4).
2. The process is killed while a re-plan is being computed: on restart the plan as last shown is intact and the queued instruction is applied once (Task 6).
3. The user sends a second instruction while the first re-plan is still running: they apply in order, one version each (Task 5).
4. The stream drops and reconnects during a re-plan: the graph ends identical to a fresh load (Task 7).
5. A plan of 40 nodes: the canvas lays it out without overlapping nodes and can be panned (Task 8).

---

### Task 1: Model client interface, fake, OpenAI-compatible client

**Files:** Create `adapters/{model.py,model_openai.py,fakes.py}`, `adapters/fake_scenarios/great_wall.json`, `tests/test_model_client.py`.

**Interfaces — produces:**
- `ModelRequest(purpose: str, tier: Literal["strong","standard","fast","verifier"], model: str, system: str, messages: list[Message], tools: list[ToolSpec] | None = None, response_schema: dict | None = None, node_ref: str | None = None)`.
- `ModelResponse(text: str, parsed: dict | None, tool_calls: list[ToolCall], usage: Usage(tokens_in, tokens_out, cost_usd: Decimal | None))`.
- `class ModelClient(Protocol): async complete(req) -> ModelResponse; def stream(req) -> AsyncIterator[str | ModelResponse]`.
- Errors: `ModelUnavailable` (timeouts, 5xx, 429), `ModelRejected(kind: Literal["key","credit"], message)` (401, 402), `ModelMalformed` (schema not satisfied).
- `OpenAICompatClient(base_url: str, get_key: Callable[[], Awaitable[str | None]])` — `POST {base_url}/chat/completions`; uses `usage.cost` when the provider returns it.
- `FakeModelClient(script: dict)` — answers by `purpose` (and `node_ref` when the script keys on it) from queues; an entry `{"raise": "unavailable"}` raises; records `calls: list[ModelRequest]`.
- `async check_model_key(client) -> KeyStatus` behind `POST /api/settings/keys/model/check` (calls `GET {base_url}/models`).

Purposes introduced in this phase: `plan.initial`, `plan.replan`.

- [ ] Tests (httpx `MockTransport`): `test_cost_taken_from_provider_when_present`; `test_401_raises_rejected_key`; `test_402_raises_rejected_credit`; `test_429_and_503_raise_unavailable`; `test_schema_violation_raises_malformed`; `test_key_never_logged` (caplog); `test_fake_serves_script_in_order_and_records_calls`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add model client interface with OpenAI-compatible and fake clients`.

### Task 2: Spend ledger

**Files:** Create `engine/budget.py`, migration `0002_graph.sql` (part), `tests/test_spend.py`.

**Interfaces — produces:**
- `async call_model(ctx: CallContext, req: ModelRequest) -> ModelResponse` — the only way engine code calls a model. Resolves `req.model` from the investigation's tier assignment, calls the client, prices the usage (`usage.cost_usd`, else the settings price table, else `0` with `approximate=True`), and returns the response plus an `EventDraft("spend.recorded", …)` in `ctx.pending_events` so it commits with the step.
- Projection: `investigations.spent_usd`, `investigations.spend_approximate`, `nodes.spent_usd`.

- [ ] Tests: `test_spend_priced_from_table_when_provider_gives_none`; `test_unknown_price_marks_approximate`; `test_spend_accumulates_on_investigation`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Record model spend per investigation and node`.

### Task 3: Graph state

**Files:** Complete `0002_graph.sql`; create `engine/ids.py`; extend `boundary/events.py`, `store/projections.py`; `tests/test_graph_state.py`.

**Interfaces — produces:**
- Tables: `nodes(id, investigation_id, display_id, parent_id, kind, question, justification, out_of_scope, done_when, depth, status, inclusion, budget, activity, verdict, brief, spent_usd, instruction_count, plan_version_added, …timestamps)`, `node_deps(node_id, depends_on_id)`, `instructions(id, investigation_id, node_id, text, state, queued_seq, applied_seq, diff, undone)`, `premises(id, investigation_id, text, node_id, outcome)`, `plan_versions(investigation_id, version, instruction_id, diff)`. All added to `STATE_TABLES`.
- Events registered: `investigation.root_goal_set`, `premise.extracted`, `node.proposed`, `node.approved`, `node.inclusion_changed`, `instruction.queued`, `instruction.applied`, `plan.version_created`, `plan.reverted`, `plan.failed`, `spend.recorded`.
- `next_display_id(kind: str, parent_display_id: str | None, taken: set[str]) -> str` per the overview rule.
- Snapshot now fills `nodes` (each with `depends_on`), `instructions`, `premises`, `plan_version`, `investigation.root_goal`.

- [ ] Tests: `test_display_ids` (`R`; `P1`, `P2`; `D1`, `D2`; child of `D2` → `D2a`, `D2b`; child of `D2b` → `D2b1`); `test_proposed_node_in_snapshot_with_deps`; `test_inclusion_change_applies_to_listed_nodes`; `test_rebuild_reproduces_graph`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add graph, instruction and premise state`.

### Task 4: Draft the plan

**Files:** Create `engine/planner.py`; handler for `draft_plan` in `engine/engine.py`; `tests/test_planner.py`.

**Interfaces — produces:**
- `PlanDraft` schema (the `response_schema` for both planning purposes): `{root_goal: str, premises: [{ref, text}], nodes: [{ref, parent_ref, kind, question, justification, out_of_scope, done_when, depends_on_refs: [str]}]}`.
- `validate_plan(draft, effort) -> list[str]` — errors for: cycle; empty justification; a premise without a `Premise check` node; node count above `effort.nodes`; depth above `effort.depth`; unknown refs.
- `async draft_plan(engine, investigation_id, command_id)`.

Behaviour: reject with `409 parallel_limit` when active investigations ≥ the setting; reject with `409 no_model_key` when no key. Emit `investigation.state_changed` Draft → Planning at once, then call `plan.initial` on the Strong tier. On an invalid or malformed plan retry up to 2 more times with the errors appended to the prompt; then emit `plan.failed` (the screen offers "Draft the plan" again). On success, one transaction: `investigation.root_goal_set`, `premise.extracted` per premise, a root node `R` (kind `Synthesis`), `node.proposed` for every node, and `plan.version_created {version: 1}`. The planner adds a dependency from every non-premise child of the root to every premise check, so premises run first (I2). The prompt is placed in the model call as delimited user data and described as hypotheses to check (P1).

- [ ] Tests: `test_draft_plan_emits_goal_premises_nodes_version` (fake script; assert event types in order and that every `D*` node depends on `P1`); `test_cycle_is_retried_then_plan_failed`; `test_node_without_justification_rejected`; `test_planning_spend_recorded` (B5); `test_no_search_or_fetch_tool_offered` (`fake.calls[0].tools is None`); `test_parallel_limit_409`; `test_root_goal_immutable` (a second `root_goal_set` for the same investigation raises in the projector).
- [ ] Fail, implement, pass.
- [ ] Commit: `Draft the initial plan from the prompt`.

### Task 5: Instruct, undo, approve

**Files:** Extend `engine/planner.py`, `engine/engine.py`; `tests/test_replan.py`.

**Interfaces — produces:**
- `compute_diff(old_nodes, new_draft) -> Diff` — matches by `ref` (existing nodes are sent to the model with their ids as refs).
- Handlers: `instruct_plan {text}`, `undo_plan_instruction`, `approve_plan`.
- `allocate_budget(effort, depth) -> NodeBudget(sources, child_nodes)` in `engine/budget.py`: `sources = max(2, round(effort.sources_per_node × 0.75 ** (depth − 1)))` (O2).

Behaviour:
- `instruct_plan`: emit `instruction.queued` (node = root). A per-investigation planning queue runs re-plans one at a time: call `plan.replan` with the current plan and every instruction so far (not undone), validate as in Task 4, then one transaction: `node.proposed` for added nodes, `node.inclusion_changed {inclusion: "Superseded", by: "replan"}` for removed ones, `instruction.applied {diff}`, `plan.version_created {version: n+1}`. If the new draft drops a premise check, keep it and add the note `"P1 kept: premises are always checked"` to `diff.notes`.
- `undo_plan_instruction`: allowed when version > 1 and no re-plan is running. Supersede what that instruction added, restore what it superseded, mark it `undone`, emit `plan.reverted {to_version: n−1}`.
- `approve_plan`: allowed in Planning with no re-plan running. Emit `node.approved` with a budget for every Included planned node (status Pending) and for `R`, then `investigation.state_changed` Planning → Running. Superseded planned nodes stay Superseded.
- All three answer `409 wrong_state` outside Planning.

- [ ] Tests: `test_instruction_adds_and_supersedes_with_diff`; `test_two_instructions_apply_in_order_as_versions_2_and_3`; `test_premise_cannot_be_removed_and_note_is_recorded`; `test_undo_restores_previous_version`; `test_undo_refused_at_version_1`; `test_approve_makes_nodes_pending_and_state_running`; `test_approve_refused_while_replanning`; `test_budget_shrinks_with_depth` (Medium: depth 1 → 8 sources, depth 3 → 4 or 5, never below 2).
- [ ] Fail, implement, pass.
- [ ] Commit: `Re-plan by instruction, undo, and approve the plan`.

### Task 6: Planning recovery

**Files:** Create `engine/recovery.py` (planning part); call it from `Engine.start()`; `tests/test_planning_recovery.py`.

- [ ] Tests: `test_restart_in_planning_restores_plan_as_shown` (snapshot before and after reopening the database are equal); `test_queued_instruction_is_applied_once_after_restart` (kill between `instruction.queued` and `instruction.applied`; after `Engine.start()` exactly one `instruction.applied` exists); `test_draft_killed_before_plan_arrives_is_redrafted` (state Planning, version 0 → planner runs again).
- [ ] Implement `async recover_planning(engine)`; pass.
- [ ] Commit: `Recover plan review after a restart`.

### Task 7: Stream store and the contract with the backend

**Files:** Backend: `tests/test_contract_golden.py` writing `contract/plan_review.json` (`{events: […], snapshot: {…}}`). Frontend: `src/api/stream.ts`, `src/state/{reduce.ts,investigationStore.ts}`, tests.

**Interfaces — produces:**
- `reduce(state: Snapshot, ev: DurableEvent): Snapshot` — a pure function with one small case per event type; ignores events with `seq <= state.seq`; unknown types only advance `seq`.
- `openStream(id, afterSeq, handlers: {onDurable, onEphemeral, onStatus(status: "open"|"reconnecting")}): () => void` — `EventSource` on `/stream?after=`; on error reopens from the last applied `seq`.
- `useInvestigation(id) → {snapshot, status, ephemeral}` (zustand): loads the snapshot, then opens the stream from `snapshot.seq`.

- [ ] Backend test: run the fake `great_wall` planning scenario (draft, one instruction, undo, instruction, approve), write events and final snapshot to `contract/plan_review.json`, and fail if the file on disk differs (regenerate with `NETGRIP_WRITE_GOLDEN=1`).
- [ ] Frontend tests: `reducing contract/plan_review.json events from an empty snapshot equals its snapshot`; `events at or below seq are ignored`; `stream reconnects from the last seq and reports "reconnecting"`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the live stream store and a shared event contract`.

### Task 8: Graph canvas and nodes

**Files:** Create `src/lib/layout.ts`, `src/ui/{GraphCanvas.tsx,GraphNode.tsx}`, tests.

**Interfaces — produces:**
- `layoutGraph(nodes: {id, parentId, dependsOn}[], opts?: {collapsed: Set<string>}) → {positions: Record<id, {x, y}>, edges: {from, to, kind: "decomposition"|"dependency", points}[], width, height}` — dagre, top to bottom, node box 172 wide.
- `<GraphNode node selected onSelect mode="plan"|"board">` — three lines as in the GraphNode README; class from status and inclusion (`ng-node--proposed`, `--excluded`, …); in `plan` mode the state word is "Planned"; `ng-node__mark` when `instruction_count > 0`; `ng-node__fold`.
- `<GraphCanvas nodes selectedId onSelect mode toolbar?>` — `ng-canvas` with the dot grid, SVG edges (`ng-edge`, `ng-edge--dep`, `ng-edge--off`, `ng-edge--live`), drag to pan, wheel to zoom, "Fit".

- [ ] Tests: `layout places parents above children and no two boxes overlap` (40-node fixture); `dependency edges get kind "dependency"`; `GraphNode in plan mode is ng-node--proposed with the word "Planned"`; `superseded node is ng-node--excluded and its edges ng-edge--off`; `selection adds is-selected and never a steer class`; `question is not shortened in the DOM` (full text present; clamp is CSS).
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the graph canvas and graph node`.

### Task 9: Composer, instructions, and the Plan review screen

**Files:** Create `src/ui/{InstructionComposer.tsx,Instruction.tsx}`, `src/lib/conclusionLike.ts`, `src/state/useCommand.ts`, `src/screens/PlanReview.tsx`; modify `NewInvestigation.tsx`; tests; `e2e/plan-review.spec.ts`.

**Interfaces — produces:**
- `useCommand(investigationId) → {send(type, opts), isSent(key): boolean}` — `isSent` stays true from click until a durable event with that `command_id` arrives.
- `conclusionLike(text: string): boolean` — true for phrasing such as "conclude that", "the answer is", "prove that", "show that it is", "make sure the report says", "it is obvious that".
- `<InstructionComposer target reach hasChildren locked? buttonLabel onSend>` — head "Instruct R · … · reaches N nodes"; foot copy from the README; foot turns `ng-warn` with "You can change what is investigated, not what is concluded. Netgrip will check this as a hypothesis." when `conclusionLike`; `⌘↵` sends; draft kept per node in `sessionStorage`.
- `<Instruction instruction nodeDisplayIds variant="queued"|"applied"|"inherited">` with its `ng-diff` (`= kept`, `↺ superseded`, `+ proposed`, notes).

**Screen behaviour, from the ScreenPlanReview README:** header with the "Plan review" pill, prompt as `title`, Spend and Planned nodes meters, "Discard draft" (deletes the investigation after the delete dialog) and steer "Approve plan and start". Centre: toolbar "Plan v3 · last instruction: +2 −1"; canvas in `plan` mode; composer docked underneath aimed at the root with button "Re-plan". Nodes added by the last instruction carry the mark "new"; nodes it removed show for that version as `ng-node--excluded` with "− Removed". Right pane: root goal; "Assumptions in your question" with each premise and its P-id and the one-sentence stance; instructions newest first with diffs; "Undo last instruction"; the "On approval" note. While a re-plan runs, the toolbar shows "Re-planning…" as an ActivityLine and Approve is disabled. `plan.failed` shows an `ng-banner--warn` with the reason and "Draft the plan" again.

`NewInvestigation`: "Draft the plan" now creates, sends `draft_plan`, and opens the investigation.

- [ ] Unit tests: `composer foot turns warn for conclusion-like text and still sends`; `button reads "Re-planning…" (is-sent) until instruction.applied arrives`; `Approve is disabled while an instruction is queued`; `diff note "P1 kept: premises are always checked" is rendered`; `exactly one ng-btn--steer on the screen`.
- [ ] End-to-end (fake mode), scenario S9: enter the Great Wall prompt → "Draft the plan" → plan graph appears with all nodes "Planned" and no `live` class anywhere → send an instruction → graph changes without reload, diff appears → "Undo last instruction" → version goes back → "Approve plan and start" → pill becomes Running.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add plan review: composer, instructions and screen`.

---

## Phase verification

- [ ] `cd backend && uv run pytest && uv run ruff check`; `cd frontend && npm test && npx tsc --noEmit && npm run e2e` — all pass.
- [ ] `git diff --exit-code contract/` after the backend tests — the golden file is current.
- [ ] Design check: `/investigations/<id>` in Planning beside `ScreenPlanReview/preview.html` at 1440×860, dark and light. Every node dashed; nothing cyan; one pink button.
- [ ] Kill test by hand: in fake mode, draft a plan, send an instruction, `kill -9` the backend, start it, reload: same plan version, instruction applied once.
- [ ] Manual live check (needs a model key): draft a plan for a real question; spend appears in the header meter and in `GET /api/investigations`.
