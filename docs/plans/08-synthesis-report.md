# Phase 8: Synthesis and report — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An investigation ends in a stored report in which every statement links to claims, nodes and sources; it is read in the app, exported as Markdown, and the investigation can be deleted with its disk space accounted for.

**Architecture:** Synthesis reads the evidence store, not node summaries (V6), and produces structured content: sections of statements, each carrying claim ids (D-16). Rules R1 and R2 are enforced in code after the model writes, not left to the prompt. The report screen renders that structure; Markdown is generated from it.

**Tech stack:** as before.

**Spec:** domain spec 4.11 (R1, R2), P1–P4, V4, V6, B3, U4, O3, I4, I6, scenarios S1, S8; tech spec section 5 "Report", "Retention and deletion", D-16, D-18, D-21; design: ScreenReport, ReportStatement, ClaimCard, Instruction READMEs.

## Global constraints

- Section order is fixed: The answer, Where you were wrong, Key findings, What could not be verified, Limits of this investigation. "Where you were wrong" is present exactly when a premise was refuted.
- Every factual statement cites at least one claim (R1). A statement resting on a claim below Confirmed is marked hedged and worded as uncertain (R2).
- Claims of Ignored, Superseded or off-topic nodes are never used. Everything the user excluded is disclosed (U4).
- The report states effort, the evidence bar used, and whether and why the run was cut short (B3, O3).
- Markdown export contains no settings and no keys.
- Nothing is pruned automatically; deletion removes only page files no other investigation uses.
- Follow "Rules for every task" in the overview.

## Review focus

1. An investigation with no usable claims (everything unobtainable, or Finish now pressed in the first minute): the report says the question could not be answered and why; it does not invent an answer (Task 2).
2. The model writes a sentence with no citation, or cites a claim id that does not exist: the sentence is removed or the synthesis retried; it never reaches the stored report (Task 2).
3. The process is killed while Synthesising: on restart synthesis runs again and exactly one report exists (Task 2).
4. Deleting an investigation while it is Running: it stops first, then deletes; no orphaned runtime keeps writing (Task 5).
5. A shared page used by two investigations survives the deletion of one, and is removed with the second (Task 5).

---

### Task 1: Report model

**Files:** Create `report/model.py`, migration `0005_report.sql`, `tests/test_report_model.py`.

**Interfaces — produces:**
- `Statement(text: str, claim_ids: list[str], hedged: bool, premise_node_id: str | None = None)`.
- `Section(key: Literal["answer","wrong","findings","unverified","limits"], title: str, statements: list[Statement])`; titles are exactly "The answer", "Where you were wrong", "Key findings", "What could not be verified", "Limits of this investigation".
- `Limits(effort: str, confirm_threshold: int, ended_early: bool, cut_short_by: Literal["budget","spending_limit","finish_now"] | None, unobtainable_pages: list[str], excluded_branches: list[{display_id, question, by}], instructions: list[{text, node_display_id, seq}], excluded_domains: list[str])`.
- `Report(id, investigation_id, created_at, answer_confidence: Literal["low","medium","high"], sections: list[Section], limits: Limits, totals: {claims, sources, nodes, spent_usd})`.
- `validate_report(report, claims: dict[str, Claim]) -> list[str]` — errors for: wrong section order or keys; a statement outside `limits` without claim ids; unknown claim id; a claim from a non-Included or off-topic node; a statement citing only claims below Confirmed with `hedged == False`; a refuted premise without a statement in `wrong`; `wrong` present with no refuted premise.
- Table `reports(id, investigation_id, created_at, body)`; one per investigation (a new synthesis replaces it); added to `STATE_TABLES`. Event `report.created` registered.

- [ ] Tests: one per validation rule, plus `test_valid_report_passes`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the structured report model and its rules`.

### Task 2: Synthesis

**Files:** Replace the body of `engine/synthesis.py`; `tests/test_synthesis.py`.

**Interfaces — produces:**
- `async gather_evidence(db, investigation_id) -> Evidence(claims, premises, contradictions)` — only claims of Included, on-topic nodes; withdrawn claims excluded.
- `build_limits(db, investigation_id) -> Limits` — computed in code from events and state, never by the model.
- `async synthesise(engine, investigation_id) -> Report` — Strong tier, purpose `synthesis.write`, given the root goal, the premises with outcomes, and the claims with status, source counts and each source's publication date (no page text, no node summaries). The prompt requires that a statement resting on dated sources says when they are from, so stale sources are not presented as current (V5). Response schema: the sections `answer`, `wrong`, `findings`, `unverified` as lists of `{text, claim_ids}` and `answer_confidence`. After the call: `hedged` is set in code from claim statuses; `validate_report` runs; on errors retry up to 2 times with the errors listed; if it still fails, drop the offending statements, and if the answer section is then empty, write the fixed statement "The evidence gathered does not answer the question." with confidence `low`. With no claims at all, skip the model call and write that statement directly. Store the report, emit `report.created`, then `investigation.state_changed` Synthesising → Completed, in one transaction.
- `finish` from Stopped: the `finish_now` handler accepts Stopped and goes to Synthesising (D-18).
- Recovery: an investigation found in Synthesising at startup runs `synthesise` again.

- [ ] Tests: `test_report_built_from_evidence_not_summaries` (the model call contains claim texts and no verdict text); `test_ignored_branch_claims_absent_and_branch_listed_in_limits` (S3, U4); `test_refuted_premise_appears_in_where_you_were_wrong` (S1); `test_no_wrong_section_without_refuted_premise`; `test_below_confirmed_statements_are_hedged` (R2); `test_uncited_statement_never_stored`; `test_unknown_claim_id_retried_then_dropped`; `test_no_claims_writes_cannot_answer_without_model_call`; `test_finish_now_marks_ended_early_in_limits` (S8); `test_budget_cut_short_stated` (O3); `test_limits_state_effort_and_threshold` (B3, V4); `test_unobtainable_pages_listed`; `test_narrowing_instructions_listed`; `test_stopped_can_be_finished_into_report`; `test_kill_during_synthesis_yields_one_report`; `test_synthesis_spend_recorded_and_respects_limit` (limit reached → Paused with `spending_limit`, state returns to Synthesising on resume).
- [ ] Fail, implement, pass.
- [ ] Commit: `Synthesise the report from the evidence store`.

### Task 3: Report queries and Markdown

**Files:** Create `api/report.py`, `report/markdown.py`, `tests/test_report_api.py`.

**Interfaces — produces:**
- `GET /api/investigations/{id}/report` → the `Report` plus `claims` (every cited claim with sources and producing node display id and path) so the screen needs one request; 404 with `code: "no_report"` before one exists.
- `to_markdown(report, claims, prompt) -> str` — the prompt, then the five sections in order; citations as footnotes `[^c12]`, each footnote listing the claim, its status and its source URLs; hedged statements keep their uncertain wording and are followed by the status in parentheses; Limits as a list.
- `GET /api/investigations/{id}/report.md` → `text/markdown` with a download filename derived from the first 60 characters of the prompt.
- List row `summary` for Completed: refuted premise count and the answer's confidence.

- [ ] Tests: `test_report_endpoint_includes_cited_claims_with_paths`; `test_markdown_has_sections_in_order_and_footnotes`; `test_markdown_contains_no_settings_or_keys` (set a key and a distinctive excluded-domain default; neither the key nor any settings field name appears; excluded domains appear only under Limits); `test_markdown_filename_is_safe` (prompt with slashes and newlines); `test_no_report_is_404`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Serve the report and its Markdown export`.

### Task 4: Report screen

**Files:** Create `src/screens/Report.tsx`, `src/ui/{ReportStatement.tsx,EvidencePane.tsx}`, tests; extend `ControlBoard.tsx`, `RunControls.tsx`.

**Behaviour, from the ScreenReport and ReportStatement READMEs:**
- Header: Completed pill with effort, preset, run time, total spend, and "ended early by you" when that applies; "Open the board"; "Export Markdown" (downloads `/report.md`).
- Left, 220px: section links with counts ("Where you were wrong · 2" in `danger`), the evidence bar in words ("Confirmed means 2 independent sources"), totals.
- Centre: `ng-report`, 680px column. The answer opens with one `display` sentence with the `ng-conf` readout above it. "Where you were wrong" is an `ng-banner--danger` directly under the answer, quoting the assumption and citing the premise node id (P1). Every factual sentence ends in `ng-cite` chips; hedged statements carry their status pill and the `ng-hedge` underline. Limits shows effort and bar, how the run was cut short, unobtainable pages, and each exclusion or narrowing as Instruction blocks.
- Right, 380px: the evidence pane for the open citation — ClaimCard, the path of nodes that produced it, where else the report uses it, and "show on the board". Closed by default; the report column then centres. The open chip is filled.
- "Open the board" opens `/investigations/:id/board` read-only with the same selection; on a Completed board the header's main button is "Open report".
- While Synthesising: the five headings with "Writing from N claims…" as an ActivityLine and no prose.

**Not built here:** the "Ask a follow-up" steer button (see the overview's last section). The screen has no steer button until that is decided.

- [ ] Tests: `sections render in the fixed order; "Where you were wrong" absent without a refuted premise`; `answer sentence is display with a confidence readout`; `every statement outside Limits ends in at least one ng-cite`; `hedged statement has ng-hedge and its pill`; `clicking a citation opens the evidence pane and fills the chip; clicking again closes it`; `evidence pane lists the node path and other uses`; `synthesising shows headings and the activity line only`; `Export Markdown links to /report.md`; `limits render instructions as Instruction blocks`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the report screen`.

### Task 5: Deletion and disk usage

**Files:** Extend `engine/engine.py` (`delete_investigation`), `store/pages.py`, `api/system.py`, `api/investigations.py`; `tests/test_delete_storage.py`.

**Interfaces — produces:**
- `async disk_usage(db, investigation_id) -> int` — bytes of its events, state rows and every page version it references; a shared page counts in full for each investigation that uses it (D-21). Cached per investigation and refreshed when its `last_seq` changes.
- `delete_investigation`: stop the runtime and wait for its tasks; in one transaction remove its events, commands, state, evidence, report, `investigation_pages` and `extractions`; then remove page versions and files that no `investigation_pages` row references. Returns the bytes freed.
- `GET /api/system/storage` reports real totals; the figure is the size on disk, so per-investigation figures may sum to more.

- [ ] Tests: `test_delete_running_investigation_stops_it_first` (no event is appended after deletion); `test_delete_removes_events_state_evidence_report`; `test_shared_page_survives_first_delete_and_goes_with_second`; `test_disk_usage_counts_shared_page_for_both`; `test_storage_total_is_on_disk_size`; `test_delete_unknown_is_404`.
- [ ] Fail, implement, pass. Frontend: the delete dialog's "frees" figure comes from `disk_bytes`; after deleting from the board, the app returns to the list.
- [ ] Commit: `Delete investigations and report disk usage`.

### Task 6: End-to-end and contract

**Files:** `e2e/report.spec.ts`; extend `contract/run.json` through `report.created` and the frontend `reduce`.

- [ ] Fake `great_wall` run to the end → the app shows the report; the first sentence says the premise was wrong; "Where you were wrong" is a danger banner citing P1; click a citation → evidence pane; "show on the board" → board opens read-only with that node selected and no pink control except node marks and log rows.
- [ ] Ignore a branch mid-run, then Finish now → the report's Limits lists the ignored branch and says "ended early by you".
- [ ] Stop an investigation; from the list choose "Finish into a report" → Synthesising → report.
- [ ] Export Markdown → the downloaded file has the five headings (or four) and footnotes.
- [ ] Delete from the list → dialog names the prompt and the space; the row is gone; `GET /api/system/storage` total decreased.
- [ ] Commit: `Add end-to-end report scenarios`.

---

## Phase verification

- [ ] `cd backend && uv run pytest && uv run ruff check`; `cd frontend && npm test && npx tsc --noEmit && npm run e2e` — all pass; `git diff --exit-code contract/`.
- [ ] Design check, dark and light: the report beside `ScreenReport/preview.html` at 1440×1110, evidence pane open and closed. Column widths 220, 680, 380.
- [ ] Anti-goals, by hand in fake mode (domain spec section 9): the report does not repeat the mistaken premise; every statement opens a claim with sources; an ignored branch is disclosed.
- [ ] Live check (manual, keys needed): one Low-effort investigation from prompt to report; open three citations and follow each to a real source URL that supports the sentence.
- [ ] Full walk through `design-system/project/screens.md` "Screens and states": each investigation state opens the screen the table names.
