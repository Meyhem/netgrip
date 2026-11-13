# Phase 6: Steering — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every intervention in domain spec 4.9 works from the board: run controls, node actions, instructions with re-plan, and the system-pause banner.

**Architecture:** Each intervention is a command handler that records events; the runtime applies them at step boundaries (E4). The interface follows the three-step life of a command in `steering.md`: click → `is-sent`; recorded → nothing changes; effect arrives as events → the screen changes.

**Tech stack:** as before.

**Spec:** domain spec 4.9, U1–U6, O4, B2, P2, P9, scenarios S3, S4, S5, S8, S10; tech spec section 6 (commands), section 9; design: `steering.md`, RunControls, NodeActions, InstructionComposer, Instruction, SystemPause READMEs, ScreenControlBoard rules and keyboard.

## Global constraints

- User interventions take precedence over the orchestrator's plan (O4).
- An instruction takes effect at the node's next step, never mid-step (E4). It applies to the node and all descendants (U1). It cannot be edited or deleted after sending.
- Instructions steer scope, never conclusions (P2, U2): in every prompt they are presented as scope guidance, and conclusion-like text is to be treated as a hypothesis to check.
- Ignored and superseded work stays visible and restorable, with the results it already produced (P9, U3).
- The root cannot be instructed after approval: `409 root_locked`.
- Confirm only re-running a node (inline, `danger`) and deleting an investigation (modal). Nothing else asks.
- Never change a pill, node or queue row before its event arrives.
- Follow "Rules for every task" in the overview.

## Review focus

1. Ignoring a branch while one of its nodes is in the middle of a fetch: the step ends cleanly, nothing of that branch starts afterwards, and its claims leave synthesis but stay stored (Task 1).
2. Restore after ignore on a branch that had completed nodes: their verdicts and claims are back without re-running (Task 1).
3. Two instructions sent to the same coordinator quickly: applied in order, one re-plan each, the second sees the result of the first (Task 3).
4. An instruction sent to a node that completes before its next boundary: it is applied to the node's record and inherited by later descendants; it is never left queued forever (Task 3).
5. Pressing `X` or `Space` while typing in the composer types a character and steers nothing (Task 6).

---

### Task 1: Ignore, restore, pause and resume a branch

**Files:** Extend `engine/{engine.py,runtime.py,scheduler.py}`, `evidence/service.py`; `tests/test_branch_interventions.py`.

**Interfaces — produces:** handlers `ignore_branch`, `restore_branch`, `pause_branch`, `resume_branch`; `branch_ids(graph, node_id) -> list[str]`.

Behaviour: `ignore_branch` emits `node.inclusion_changed {node_ids: branch, inclusion: "Ignored", by: "user"}`; running nodes of the branch get the `cancel` signal at their next boundary and return to Pending without losing committed work; non-Included nodes are never eligible; their claims are excluded from `known_claims` and from synthesis. `restore_branch` sets the branch back to Included (also for Superseded branches); Completed nodes keep their output. `pause_branch` emits `node.paused {node_ids}`; `resume_branch` emits `node.resumed`. A coordinator whose remaining Included children are all finished can aggregate (G3). All four are refused on the root with `409 use_investigation_controls`.

- [ ] Tests: `test_ignore_stops_branch_and_excludes_claims` (S3); `test_ignore_mid_step_finishes_step_then_stops`; `test_restore_brings_back_results_without_rerun` (no new model calls for completed nodes); `test_restore_superseded_branch`; `test_pause_branch_leaves_rest_running`; `test_resume_branch`; `test_coordinator_aggregates_without_ignored_children`; `test_duplicate_ignore_is_noop`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add ignore, restore, pause and resume for a branch`.

### Task 2: Run only this branch, go deeper, re-run, finish now

**Files:** Extend `engine/{engine.py,scheduler.py,budget.py,runtime.py}`; `tests/test_focus_budget_rerun.py`.

**Interfaces — produces:** handlers `run_only_branch`, `run_everything`, `go_deeper`, `rerun_node`, `finish_now`; `GO_DEEPER = {"depth": +1, "child_nodes": ×1.5 rounded up, "sources": ×1.5 rounded up}` applied to the branch (B2); the investigation's node ceiling rises by the added child nodes.

Behaviour: `run_only_branch` emits `focus.changed {node_id}`; nodes outside the branch are not eligible and get the wait reason `focus:<id>`; running steps outside finish their step and return to Pending. `run_everything` emits `focus.changed {node_id: null}`. `go_deeper` emits `node.budget_changed {cause: "go_deeper"}` for the branch. `rerun_node` is allowed for Completed or Failed nodes: emits `node.reset {reason: "rerun"}`, clears the verdict, emits `claim.withdrawn {claim_ids, cause: "rerun"}` for the node's own claims (their sources stay; pages and extractions are reused; withdrawn claims are not used in briefs or synthesis), and leaves children as they are. `finish_now` is allowed in Running or Paused: no new node starts, running steps finish, state → Synthesising with `ended_early: true` recorded for the report (S8).

- [ ] Tests: `test_focus_runs_only_branch_and_reasons_say_so` (S5); `test_run_everything_resumes_rest`; `test_go_deeper_raises_branch_budget_and_allows_more_children`; `test_rerun_resets_node_reuses_pages_and_extractions`; `test_rerun_refused_for_running_node` (`409 wrong_state`); `test_finish_now_goes_to_synthesising_and_marks_ended_early`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add focus, go deeper, re-run and finish now`.

### Task 3: Instructions on a running investigation

**Files:** Extend `engine/{engine.py,agent.py,planner.py,brief.py}`; `tests/test_instructions.py`.

**Interfaces — produces:** handler `add_instruction {text}`; `async apply_instructions(ctx) -> None` called inside `ctx.boundary()`; `async replan_children(ctx, coordinator, instruction) -> Diff` (Standard tier, purpose `node.replan`, reusing `compute_diff` and the validation from Phase 3).

Behaviour:
- Queue: `instruction.queued {waiting_for}` where `waiting_for` names what it waits on ("D2b finishes READING" for a running node; null when the node is idle).
- Apply at the target's next boundary; when the target is not Running (Pending, Waiting on children, Completed), apply at once. Emit `instruction.applied {at_step, diff}` and raise the node's `instruction_count`.
- A target with children re-plans: fitting children are kept with their results; unfitting ones get the `cancel` signal and `node.inclusion_changed {inclusion: "Superseded", by: "replan", instruction_id}`; new children are emitted as `node.proposed` and go through the orchestrator as usual. No confirmation (U5).
- A Completed target with an applied instruction that changes its children returns to Waiting on children and aggregates again.
- Running descendants see the instruction in their brief from their next step; their trail records the boundary (`trail[].instruction_applied`).
- Root after approval → `409 root_locked`.

- [ ] Tests: `test_instruction_waits_for_step_boundary` (the step in progress completes with the old brief; the next step's model call contains the instruction); `test_instruction_on_coordinator_keeps_supersedes_proposes` (S4: five children, instruction to concentrate on one site → four Superseded, kept child keeps its claims, new children Proposed); `test_superseded_children_restorable`; `test_instruction_inherited_by_descendants_briefs`; `test_two_instructions_apply_in_order`; `test_instruction_on_node_that_completes_first_is_applied_not_stuck`; `test_root_locked_after_approval`; `test_instruction_text_is_framed_as_scope_not_conclusion` (the prompt section heading for instructions and the hypothesis sentence are present in the model call).
- [ ] Fail, implement, pass.
- [ ] Commit: `Apply instructions at step boundaries and re-plan coordinators`.

### Task 4: Run controls and the life of a command in the interface

**Files:** Create `src/ui/RunControls.tsx`; extend `src/state/useCommand.ts`, `BoardHeader.tsx`, `Investigations.tsx`; tests.

**Behaviour, from the RunControls README:** controls by state — Planning: Approve plan (steer), Discard draft; Running: Pause, Finish now, Stop; Paused: Resume (steer), Finish now, Stop; Synthesising: none; Stopped: Resume (steer), Finish into a report; Completed: Open report, Export Markdown. `is-sent` wording: "Pausing…", "Resuming…", "Stopping…", "Finishing…". No confirmation on any of them. With focus on, the header's mono line reads "Running only D2" with a "Run everything" button. The Investigations list actions (Pause, Resume, Finish into a report) now send their commands.

`useCommand` gains `settledBy`: the control leaves `is-sent` when an event with the command's id arrives, or on a 409 (the message is shown in an `ng-banner--warn` for 6 s). While the stream is reconnecting, commands still send and controls stay `is-sent`.

- [ ] Tests: `controls per state` (table over seven states); `exactly one steer button when the investigation waits for the user`; `Pause shows "Pausing…" and the pill stays Running until the state event arrives`; `409 shows the server message and restores the button`; `no confirmation dialog opens for Stop or Finish now`; `focus line and Run everything`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add run controls with acknowledged-then-effect behaviour`.

### Task 5: Node actions, menu and keyboard

**Files:** Create `src/ui/NodeActions.tsx`, `src/lib/keys.ts`; extend `Inspector.tsx`, `ExecutionOrder.tsx`, `ControlBoard.tsx`; tests.

**Interfaces — produces:**
- `actionsFor(node, investigation) → Action[]` where `Action = {type, label, key, enabled, consequence}` — the "Applies when" column of the NodeActions README: Add instruction always, except the root once research has started; Go deeper when Included; Run only this branch when the investigation is Running; Pause when Pending, Running or Waiting on children, Resume when Paused; Ignore or Restore always; Re-run when Completed or Failed. Items that do not apply stay in the list with `enabled: false` and the reason as `consequence`. Enabled items name the scope: "this node and its 4 descendants". Special cases from ScreenNodeDetail: Rejected → the only action is "Add instruction" on the parent; not Included → "Restore branch" is the steer button of the Overview.
- `useBoardKeys(handlers)` — `I` instruct, `D` go deeper, `F` run only this branch (again: run everything), `Space` pause or resume branch, `X` ignore or restore, `R` re-run, `L` log, `.` node menu, `Esc` clear selection. Ignored while focus is in an input, textarea or contenteditable, or while a modifier key is held.

**Behaviour, from the NodeActions README and `steering.md`:** the inspector's action row shows the four most used actions; the rest are in the node menu (`ng-menu`, opened by `.` or the row's overflow). Each action states its consequence and scope in its hint ("Stops it and keeps its findings out of the report. You can restore it." "Reaches 4 nodes."). Re-run asks inline in the inspector with an `ng-banner--danger` and a `ng-btn--danger` "Re-run node". Not running rows gain their "Restore" link. After `go_deeper`, the branch meters show the higher limit when the event arrives.

- [ ] Tests: `actionsFor per node state` (table); `X sends ignore_branch for an included node and restore_branch for an ignored one`; `keys do nothing while typing in the composer`; `re-run shows an inline danger confirmation and sends only after it`; `ignore shows "Ignoring…" until the event, then the node is ng-node--excluded with the pill "Ignored by you"`; `Restore link in Not running sends restore_branch`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add node actions, node menu and keyboard steering`.

### Task 6: Composer on the board and instruction states

**Files:** Extend `InstructionComposer.tsx`, `Instruction.tsx`, `Inspector.tsx`, `Trail.tsx`; tests.

**Behaviour, from the InstructionComposer README and `steering.md` "Instructing a node":** the composer is pinned to the bottom of the inspector and aims at the selected node: "Instruct D2 · What astronauts report · reaches 4 nodes". Foot copy: with children, that a re-plan follows at once and each superseded child can be restored; without, "Takes effect at the node's next step". Sending shows the instruction above the composer as `ng-instr--queued` with `waiting_for` ("applies when D2b finishes READING"); on `instruction.applied` it becomes the filled `ng-instr` with its sequence number and, for a coordinator, the `ng-diff` with a Restore button per superseded child; descendants list it as `ng-instr--inherited` "from D2". The node gains the mark "✎︎ 1". The root's composer after approval is `is-locked` with the README's explanation. In Synthesising, Completed and Stopped every composer is locked. `I` focuses it; `Esc` returns focus to the graph and keeps the draft; drafts are per node.

- [ ] Tests: `head names target and reach`; `queued → applied → inherited states render with their classes`; `diff rows = kept, ↺ superseded with Restore, + proposed`; `root composer is locked after approval with the explanation`; `draft survives changing selection and coming back`; `Esc keeps the draft`; `clicking the sequence number scrolls the log to that row`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Steer nodes with instructions from the board`.

### Task 7: System pause banner and recovery notice

**Files:** Create `src/ui/SystemPause.tsx`; extend `ControlBoard.tsx`, `Investigations.tsx`; tests.

**Behaviour, from the SystemPause README and `steering.md` "When Netgrip stops by itself":** when the investigation is Paused with `origin: system`, a banner sits between the header and the panes and pushes them down. It states the cause, what Netgrip did, and the choices:
- `spending_limit` → `warn`; a new-limit field (default: the current limit plus the default limit) with "Raise limit and resume" (steer; sends `raise_limit` then `resume`), "Finish now", "Stop".
- `model_unavailable`, `search_unavailable` → `warn`; "Resume" (steer) and "Show the errors in the log" (sets the log filter to Problems); body: "Netgrip stopped retrying so it would not spend without progress. Nothing is lost."
- `key_rejected`, `credit_exhausted` → `danger`; the provider's message; "Open Settings → Keys"; "Resume" stays disabled until the key's status is no longer rejected.

The title starts with "Paused:" and states the cause in plain words. The banner cannot be dismissed while the investigation is paused by the system. A user pause shows no banner. While a system banner shows, the header's Resume is not steer (one pink button per view). After a restart, when a `system.recovered` event is newer than the last one this browser has seen for that investigation, show once a neutral banner with "Dismiss": "Picked up where it stopped."

- [ ] Tests: `banner per cause with its tone and choices`; `raise limit sends raise_limit then resume, in that order, and shows is-sent until Running`; `Resume disabled while the key is rejected`; `no banner for a user pause`; `only one steer button while the banner shows`; `recovery notice shows once per recovery and can be dismissed`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the system pause banner and recovery notice`.

### Task 8: End-to-end steering

**Files:** `e2e/steering.spec.ts`; extend `contract/run.json` scenario with interventions and the frontend `reduce` for `node.paused`, `node.resumed`, `node.budget_changed`, `focus.changed`.

- [ ] S3: select a branch, press `X` → greys and hatches, appears under Not running, log has a pink `You` row; Restore → returns.
- [ ] S4: instruct a coordinator → queued, then applied with a diff; superseded children hatched; new children dashed, then approved.
- [ ] S5: `F` → header "Running only …"; other rows read "waits: you are running only …"; "Run everything" clears it.
- [ ] S8: Finish now → pill Synthesising, composer locked.
- [ ] S10 (fake scripted outage, `NETGRIP_FAKE_SCENARIO=outage`, retry window shortened by a test setting): banner appears with the cause; Resume continues to the end.
- [ ] Spending limit (fake scenario with limit `$0.05`): banner; raise the limit; run continues.
- [ ] Pause then reload: still Paused "by you", Now empty with "Nothing runs while paused".
- [ ] Commit: `Add end-to-end steering scenarios`.

---

## Phase verification

- [ ] `cd backend && uv run pytest && uv run ruff check`; `cd frontend && npm test && npx tsc --noEmit && npm run e2e` — all pass; `git diff --exit-code contract/`.
- [ ] Walk the two tables in `design-system/project/steering.md` ("Investigation level", "Node level") by hand in fake mode; each row's "What the user sees" happens, and only after its event.
- [ ] Design check: board with a queued and an applied instruction beside `InstructionComposer/preview.html` and `Instruction/preview.html`; paused-by-system board beside `SystemPause/preview.html`.
- [ ] Count pink: on a running board with nothing sent, the composer is the only pink control.

## Carried from Phase 4

- `node.completed` does not reset the relevance-gate marker (`relevance_checked`), so after a rerun the gate is not owed again after a kill: reset it on `node.reset` / `node.started`.
- The runtime reads `effort.parallel` once per launch: an effort change must make it read it again.
- A pause while the runtime drains records nothing durable until the drain ends, so a kill in that window resumes as Running: consider a durable "pausing" marker.
- The model and search limiters are resized only on GET /pools and at start: resize them on the settings PATCH too.
- A Rejected dependency leaves its dependant Pending forever (reason `dependency:<id>`) while the run still concludes: treat Rejected like a dependency left Failed (run, with a note in the brief), or show the node as not run.
- Return work that hits an unexpected error stays owed and the investigation stays Running with no live loop and no visible cause until a resume or restart: record it as a system pause with a cause the board can show.

## Carried from Phase 5

- `useBoardKeys` must replace ControlBoard's ad-hoc `L`/Escape window listener (`ControlBoard.tsx`), so there are not two key handlers. Reconcile what Escape means: the spec says it clears the selection; below 1180px it now closes the inspector sheet.
- `instruction.applied` on a node with no trail steps yet is silently dropped from the trail (`_trail_instruction` in `store/projections.py`). Instructing a Pending node will hit this: keep the rule for the node's first step.
- Reveal and pan to a selected node that sits inside a fold or is hidden by Show excluded off.
- An excluded node still marked Running must not get a live pill (Phase 5 gates the inspector pill and trail verbs on Included + Running/Waiting + investigation not Paused/Stopped): verify it when Ignore can hit a running branch.
