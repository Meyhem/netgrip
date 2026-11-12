# Phase 2: App shell and first screens — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The React app exists, is styled only by the design system, and has three working screens: Investigations, New investigation, Settings.

**Architecture:** A single-page app that loads `tokens.css` and `components/bundle.css` straight from `design-system/project` and renders `ng-` classes. One thin React component per design-system component. All state comes from the API; nothing is optimistic.

**Tech stack:** React 18, TypeScript, Vite, react-router, zustand, vitest, @testing-library/react, Playwright.

**Spec:** `design-system/project/README.md`, `screens.md`, and the READMEs and previews of ScreenInvestigations, ScreenNewInvestigation, ScreenSettings, Button, Field, StatusPill, ActivityLine, BudgetMeter. `docs/plans/00-overview.md`.

## Global constraints

- No CSS colour, font or radius literals in `frontend/src`; tokens only. No icon set, no emoji; glyphs are the Unicode characters in the brand book.
- One `ng-btn--steer` per view.
- Money is `$1.84 / $5.00`: dollar sign, two decimals. Counts carry limits: `9 / 16 nodes`.
- Sentence case; no "please", "sorry", "successfully"; the system is "Netgrip".
- The theme follows the system (`prefers-color-scheme`); there is no toggle.
- A key is never displayed, not even masked.
- Follow "Rules for every task" in the overview.

## Review focus

1. The API is unreachable when a screen opens: the screen says so in an `ng-banner--warn` and retries; it does not render an empty table as if there were no investigations (Task 5).
2. A prompt of several thousand characters in a list row: clipped by CSS to one line, full text in `title`; the table does not grow sideways (Task 5).
3. Typing a non-number into a Settings number field: the field shows `is-error`, nothing is saved, the previous value stays on the server (Task 7).
4. Double-clicking "Save as draft": one investigation is created (same command id reused) (Task 6).
5. Light theme: every screen readable with `prefers-color-scheme: light` (phase verification).

---

### Task 1: Scaffold and design-system wiring

**Files:** Create `frontend/{package.json,vite.config.ts,tsconfig.json,index.html,playwright.config.ts}`, `frontend/src/{main.tsx,App.tsx,app.css}`, `frontend/src/design.contract.test.ts`. Modify `.gitignore` (`frontend/node_modules/`, `frontend/dist/`, `frontend/test-results/`).

**Interfaces — produces:**
- Vite alias `@ds` → `../design-system/project`; `main.tsx` imports `@ds/tokens.css` then `@ds/components/bundle.css`; `index.html` has `<body class="ng">` and the Google Fonts link for Instrument Sans and JetBrains Mono.
- Dev proxy `/api` → `http://127.0.0.1:8321`.
- Scripts: `dev`, `build`, `test` (`vitest run`), `e2e` (`playwright test`). Playwright `webServer` starts `NETGRIP_FAKE=1 NETGRIP_DATA_DIR=<temp> uv run netgrip` from `../backend` after `npm run build`.
- `app.css` holds layout only (grid areas, widths from the screen READMEs) using `var(--…)` tokens.

- [ ] Write `design.contract.test.ts`: (a) collect every `ng-[a-z0-9-]+(--[a-z0-9-]+)?(__[a-z0-9-]+)?` token in `src/**/*.{tsx,ts,css}` and assert each appears in `bundle.css`; (b) assert no match of `#[0-9a-fA-F]{3,8}\b`, `rgb\(`, `hsl\(` or `font-family:` in `src/**`.
- [ ] `npm test` — passes on the empty app; `npm run build` succeeds.
- [ ] Commit: `Scaffold the frontend on the design system`.

### Task 2: API client and types

**Files:** Create `src/api/{types.ts,client.ts}`, `src/api/client.test.ts`.

**Interfaces — produces:**
- Types mirroring Phase 1: `InvestigationRow`, `Snapshot`, `DurableEvent`, `Settings`, `KeyStatus`, `Pools`, `Storage`, and the string unions from the overview's "State strings".
- `getJSON<T>(path): Promise<T>`; `patchJSON`, `putJSON`; `ApiError {status, code, message}`.
- `sendCommand(investigationId, type, opts?: {nodeId?, payload?, id?}): Promise<{recorded, duplicate}>` — generates `crypto.randomUUID()` once and resends the same id on a network error (up to 3 times).
- `createInvestigation(id, prompt, settings)`; `deleteInvestigation(id)`.

- [ ] Tests (fetch mocked): `sendCommand retries with the same id after a network error`; `409 becomes ApiError with code`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add typed API client with idempotent commands`.

### Task 3: Base components and vocabulary

**Files:** Create `src/ui/{vocab.ts,Button.tsx,Field.tsx,StatusPill.tsx,ActivityLine.tsx,BudgetMeter.tsx,Banner.tsx}`, `src/lib/format.ts`, tests beside each.

**Interfaces — produces:**
- `vocab.ts`: `INVESTIGATION_PILL: Record<InvestigationState, {glyph, word, tone, pulses?}>`, `NODE_PILL`, `INCLUSION_PILL`, `CLAIM_STATUS`, `KIND_CODE`, `PAUSE_ORIGIN: Record<PauseCause, string>` ("by you", "spending limit", "model service unavailable", "search unavailable", "key rejected", "credit exhausted").
- `<Button variant="default"|"steer"|"quiet"|"danger" size? sent? sentLabel?>` — when `sent`, shows `sentLabel` with class `is-sent` and is disabled.
- `<Input>`, `<Textarea>`, `<Seg options value onChange>`, `<Toggle>`, `<NumberField value onCommit>`, `<KeyField status onReplace>`.
- `<StatusPill kind="investigation"|"node"|"inclusion" state origin?>`; `<ActivityLine activity detail retry?>`; `<BudgetMeter label value max format="money"|"count" approximate?>` (adds `ng-meter--warn` above 80%, `--danger` at 100%, "≈" when approximate); `<Banner tone>`.
- `format.ts`: `money(n) → "$1.84"`, `moneyOf(a, b) → "$1.84 / $5.00"`, `duration(seconds) → "1h 12m"`, `bytes(n) → "387 MB"`.

- [ ] Tests: `vocab.test.ts` asserts every row of the StatusPill README tables (for example `Planning → {glyph: "✎︎", word: "Plan review", tone: "steer"}`, `Waiting on children → {glyph: "◔", tone: "live", hollow: true}`, `Rejected → ⊘ danger hollow`) and that the pill renders glyph plus word; `Paused` pill renders its origin; `BudgetMeter` at 85% has `ng-meter--warn`; `money(1.8) === "$1.80"`.
- [ ] Fail, implement, pass. Markup follows each component's `preview.html`.
- [ ] Commit: `Add base components and the state vocabulary`.

### Task 4: App shell and routes

**Files:** Create `src/ui/TopBar.tsx`, `src/screens/InvestigationRoute.tsx`; modify `App.tsx`; tests.

**Interfaces — produces:**
- Routes: `/` Investigations; `/new`; `/investigations/:id` (chooses the screen from the investigation state, per `screens.md`: Draft → NewInvestigation with the draft loaded; Planning → PlanReview; Running, Paused, Stopped, Synthesising → ControlBoard; Completed → Report); `/investigations/:id/board`; `/settings`. Screens not built yet render a `Banner` naming the state.
- `<TopBar>`: `ng-top` with the `ng-brand` wordmark, nav links, and the pools readout from `GET /api/system/pools` polled every 5 s: `models 5/8 · search 1/4 · browsers 4/6 · today $3.12` in mono.

- [ ] Tests: `TopBar renders pools from the API in the README's format`; `route /investigations/:id picks the screen by state`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add app shell, top bar and routing`.

### Task 5: Investigations screen

**Files:** Create `src/screens/Investigations.tsx`, `src/ui/{Table.tsx,DeleteDialog.tsx}`, tests.

**Behaviour, from the ScreenInvestigations README:**
- Title row: `display` title; "N active of 5 allowed" (Running, Planning, Synthesising and Paused count as active); total disk; steer button "New investigation", key `N`.
- Filter `ng-seg`: All, Needs you, Running, Finished; search input filters by prompt text.
- Columns: Prompt, State, Effort, Nodes, Spend, Disk, Run time, action.
- Row line 2 (mono) by state, from `row.summary`; Paused shows the reason in `ng-warn` and "Nothing is lost".
- One action per state: Draft → "Continue"; Planning → "Review plan" (steer); Running → "Pause"; Paused → "Resume" (steer); Stopped → "Finish into a report"; Completed → "Open report". Actions whose command arrives in a later phase navigate to the investigation instead.
- "Needs you" = Planning or Paused. `document.title` is `(2) Netgrip` when the count is 2, else `Netgrip`.
- Sort: needs you, then Running, then `last_activity_at` descending.
- Overflow menu holds "Delete investigation" → `DeleteDialog` on `scrim`, naming the prompt and `bytes(disk_bytes)`, with an `ng-btn--danger` button.
- Empty state: no table; the prompt box and the line "Ask a question or state a claim. Netgrip will check it, including the parts you take for granted."
- List refreshes every 3 s.

- [ ] Tests: `sorts needs-you first`; `sets the tab title to the needs-you count`; `one action button per row, chosen by state` (table-driven over all seven states); `Paused row shows cause and "Nothing is lost"`; `empty state shows the prompt box and no table`; `API failure shows a warn banner, not the empty state`; `delete dialog names prompt and freed space and calls DELETE`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the Investigations screen`.

### Task 6: New investigation screen and cost estimate

**Files:** Backend: create `engine/estimate.py`, add `POST /api/estimate` to `api/settings.py`, `tests/test_estimate.py`. Frontend: create `src/screens/NewInvestigation.tsx`, tests.

**Interfaces — produces:**
- `estimate(effort: EffortBudget, tiers: dict[str, str], models: list[ModelPrice]) -> Estimate(low_usd, high_usd, per_tier: {tier: {low_usd, high_usd, share}}, unpriced_models: [str])`. High bound: `nodes × TOKENS_PER_NODE[tier]` priced per model, with Fast multiplied by `sources_per_node`. Low bound: `0.4 × high`. `TOKENS_PER_NODE` (in, out), placeholders to tune with D-20: strong `(6000, 1500)`, standard `(30000, 4000)`, fast per source `(8000, 800)`, verifier `(3000, 500)`.
- `POST /api/estimate {effort, tiers}` → `Estimate`.
- Investigation `settings` shape: `{effort: "Low"|"Medium"|"High", preset, tiers: {strong, standard, fast, verifier}, excluded_domains: [str], prefer: "none"|"primary", page_reuse: "1d"|"always_refetch", spending_limit_usd}`.

**Behaviour, from the ScreenNewInvestigation README:** left column in the fixed order (prompt, Effort with the resulting budget line in mono, Models preset and four-row tier table with what each tier does and its share, source filters, page reuse, spending limit); right column sticky with the range in `display`, the per-tier split, "What happens next" and the steer button "Draft the plan"; secondary "Save as draft". Every default comes from `GET /api/settings`. Warnings: unpriced model → `ng-warn` "No price on record. The spending limit will be approximate" with a link to `/settings#models`; Verifier sharing a model family (text before `/`) with Strong → `ng-warn`. With no model key, "Draft the plan" is disabled and the hint reads "Add a model key in Settings → Keys".

In this phase "Draft the plan" creates the investigation and opens `/investigations/:id`; Phase 3 Task 9 adds the `draft_plan` command to it.

- [ ] Backend tests: `test_estimate_is_a_range_low_below_high`; `test_unpriced_model_listed`; `test_shares_sum_to_one`.
- [ ] Frontend tests: `defaults come from settings`; `effort line reads "depth 4 · 40 nodes · 8 sources/node · 4 in parallel · 2 independent sources to confirm" for Medium`; `estimate shows a range and the words "An estimate, not a quote"`; `Draft the plan is disabled without a model key, with the hint`; `double click on Save as draft creates one investigation`; `verifier family warning`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the New investigation screen with cost estimate`.

### Task 7: Settings screen

**Files:** Create `src/screens/Settings.tsx`, tests.

**Behaviour, from the ScreenSettings README:** one scrolling page, section list at the left (`ng-settings`), sections Keys, Models, Effort, Spending, Sources, Capacity, Storage with ids matching (`#keys`, `#models`, …). Each field saves on commit with `PATCH /api/settings`; there is no Save button. Keys: `KeyField` rows showing "Key set", "No key" or "Key rejected" with the provider's message, and one button "Replace" that reveals an empty input; the stored key is never requested. Models: per-model table; a model with no price has empty `is-error` price inputs and a `warn` note. Effort: editable numbers, labelled as starting values. Capacity: each limit with what is in use now, in mono, from `GET /api/system/pools`. Storage: totals, data location, and "Rebuild state from history" (`POST /api/system/rebuild`), which reports "Rebuilt from N events."

- [ ] Tests: `changing Medium max nodes sends PATCH with only that field`; `non-numeric input shows is-error and sends nothing`; `key row shows status words and never an input value from the server`; `Replace sends PUT and clears the input`; `rebuild shows the event count`; `no theme, account or notification section exists`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the Settings screen`.

### Task 8: End-to-end

**Files:** Create `frontend/e2e/{foundation.spec.ts,helpers.ts}`.

- [ ] `empty state → type a prompt → Save as draft → row appears as Draft with "Continue"`.
- [ ] `Settings: change the spending limit to $7.50, reload, it reads $7.50; New investigation defaults to $7.50`.
- [ ] `Settings: set a model key; the page HTML and every /api response body never contain the key string` (collect responses with `page.on("response")`).
- [ ] `delete a draft: dialog names the prompt; row disappears`.
- [ ] `npm run e2e` passes. Commit: `Add end-to-end tests for the first screens`.

---

## Phase verification

- [ ] `cd frontend && npm test && npx tsc --noEmit && npm run e2e` — all pass. `cd backend && uv run pytest` — still passes.
- [ ] Design check, dark and light (switch the system theme or use the browser's rendering emulation): open `/`, `/new`, `/settings` beside `design-system/project/components/ScreenInvestigations/preview.html`, `ScreenNewInvestigation/preview.html`, `ScreenSettings/preview.html` at 1440×760, 1280×1130, 1280×1960. Regions, order, type roles and colours match the numbered regions in each README. Exactly one pink button per screen.
- [ ] `npm run build`, then start only the backend and open `http://127.0.0.1:8321/`: the app loads from the backend (A-05).
