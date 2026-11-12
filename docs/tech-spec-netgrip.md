# Tech Spec: Netgrip

*Drafted 2026-11-12 from an interview with the project owner. Status: draft.*
*Domain reference: [domain-spec.md](domain-spec.md). Rule IDs such as P6, E4, V8 refer to that document.*

## 1. What this is

Netgrip is a locally run deep web research application. A Python backend runs investigations: an orchestrator and a set of node agents that search the web, fetch pages, extract sourced claims and synthesise a report. A React frontend shows the task graph forming in real time and lets the user intervene.

It is one backend process and one browser tab on the same machine. The backend calls three kinds of external service: AI model providers, a web search API, and the open web through a headless browser. It owns all of its own data: event history, graph state, evidence, fetched pages and settings.

## 2. Constraints

Given, not chosen.

- **C-01** — Backend is Python, managed with uv. (Owner.)
- **C-02** — Frontend is React, built with Vite. (Owner. "Vite" was inferred from a cut-off message; see A-01.)
- **C-03** — Runs locally only. Hosting is undecided and out of scope. (Owner.)
- **C-04** — The browser is always on the same machine as the backend. (Owner.)
- **C-05** — Single user; no accounts, authentication or sharing. (Domain spec I3, non-goals.)
- **C-06** — 2 to 5 investigations must be able to run in parallel. (Owner.)
- **C-07** — The host machine has about 16 GB of RAM. (Owner.)
- **C-08** — Models are reached through OpenRouter initially, and the system must not be tied to one provider. (Domain spec M5, Appendix A.)
- **C-09** — Web search goes through a search API; Tavily was named. Fetching uses Playwright; Crawl4AI is under consideration for Markdown extraction. (Domain spec Appendix A.)
- **C-10** — Raw material is kept until the user deletes the investigation. (Owner.)

## 3. Quality targets

- **N-01** — Scale envelope per investigation at High effort: tens of nodes, hundreds of fetched pages. (Owner.)
- **N-02** — Run length is unbounded and unpredictable; multi-hour unattended runs are normal. (Owner.)
- **N-03** — Durability: a process kill at any moment loses no completed node, no stored claim and no fetched page (P6). Work lost is at most the in-flight steps of running nodes.
- **N-04** — Recovery is automatic: on restart, investigations that were Running continue without user action (domain spec 6.1).
- **N-05** — Degradation preference: when a dependency is unavailable, prefer paused over failed, and never prefer spending money without progress (D-08, D-09).
- **N-06** — Live view latency: unmeasured. Target is that a state change reaches the open browser in well under a second on localhost.
- **N-07** — Availability, RTO and RPO as service targets do not apply; this is a single-user local tool.

## 4. Architecture

One backend process hosts two parts separated by an internal boundary.

**API layer.** Serves the frontend's HTTP requests: reading state, submitting interventions, managing settings, and holding the live event stream open. It contains no research logic. It talks to the engine only through the boundary below.

**Engine.** Runs investigations. It contains:

- **Investigation runtime** — one per active investigation. Holds the in-memory graph, schedules eligible nodes (G2), applies interventions at step boundaries (E4), enforces budgets and the money cap.
- **Orchestrator** — one per investigation. Approves or rejects proposed nodes, allocates budget, decides when to conclude (domain spec 4.3).
- **Node agent loop** — our own loop, not a framework (D-03). A node runs as a sequence of discrete steps: plan, search, read, extract, reason, propose, aggregate. Each step ends by emitting events. Step boundaries are the only points where pause, instruction and cancellation take effect.
- **Evidence service** — stores sources and claims, judges independence (V2), records contradictions (V3).
- **Shared resource pools** — global across all investigations: a model call limiter, a search limiter and a browser pool. These are what make 2–5 parallel investigations safe on one machine (D-05).

**The boundary** between API and engine is two things only: *commands* in (start, pause, add instruction, ignore branch, and so on) and *events* out. Nothing else crosses. This is the seam that lets the engine move to a separate process later without redesign (section 12).

**Adapters.** Each external capability sits behind an interface with one initial implementation:

| Interface | Initial implementation | Why it is a seam |
|---|---|---|
| Model client | Generic OpenAI-compatible client, pointed at OpenRouter | M5; local models later (D-04) |
| Search | Tavily | Named, not committed |
| Fetcher | Escalating: plain HTTP, then Playwright, then hardened Playwright (W2) | Fetch strategies will change |
| Content extractor | HTML to clean text/Markdown (Crawl4AI candidate) | Undecided library |

**Frontend.** A React single-page app. It loads a state snapshot, then applies events from the stream. It never computes research state itself; it renders what the backend says and sends commands.

**Browser control.** Driving a real browser is the least reliable part of the system: pages hang, navigations time out, tabs crash, the browser process dies or stops answering, and a cancelled task can leave a browser running. The design treats all of this as normal (D-22):

- *One owner.* Only the browser pool starts or stops browsers. A node borrows an isolated browsing session for one fetch and never holds a browser across steps.
- *Every operation has a deadline.* Navigation, waiting for content and reading it each have a time limit, and the fetch as a whole has an overall limit. Nothing waits indefinitely on a page.
- *Cleanup is guaranteed, not best-effort.* A borrowed session is closed on every exit path — success, error, timeout, and cancellation by pause, stop or shutdown. A session that cannot be closed cleanly takes its browser with it: the pool kills that browser process and starts a fresh one.
- *Nothing is reused after a fault.* A session that timed out or crashed is discarded, never returned to the pool. Browsers are also recycled after a fixed amount of use, so slow memory growth cannot accumulate over a multi-hour run.
- *The pool heals itself.* A dead or unresponsive browser is detected, replaced, and the fetches that were on it are retried under W1. A browser fault is a transient fetch failure; it never fails a node (E5) and never pauses an investigation.
- *No orphans.* On shutdown the pool closes every browser it started. On startup it removes browser processes and temporary profile data left behind by a previous run that was killed.
- *Visible.* Retries appear on the node as activity (W1). Pool health — browsers running, restarts, fetches timed out — is in the application log.

**Untrusted content (P7).** Fetched page text only ever enters a model call as clearly delimited data. Calls that read page content (Fast tier extraction) have no tools at all. Node agents have a closed tool set: search, fetch, record claim, propose node. No tool touches the file system, a shell, or arbitrary network destinations beyond fetching a URL for reading.

## 5. Data

**Stores**

| Store | Holds | Source of truth for |
|---|---|---|
| SQLite database (one file, WAL mode) | Event log, state tables, evidence, page index, settings | Everything except page bodies |
| Page files on disk (content-addressed) | Raw and cleaned bodies of fetched pages | Page content |

**Event log.** Append-only, one ordered sequence per investigation. Every state change is an event: node proposed, approved, started, activity changed, claim added, intervention applied, budget changed, investigation paused with reason. The event log is the source of truth (D-06).

**State tables.** Current graph, node status and inclusion, evidence, budget spent. Updated in the same database transaction as the event that caused the change, so the two cannot disagree. They can be rebuilt from the log; a rebuild command exists for repair and for schema changes.

**Transactional boundary.** One step's outcome — its events and its state changes — commits atomically. A step either fully happened or did not happen.

**Not persisted.** Token-by-token model output. It is streamed to the browser for an open node and discarded; the finished step is stored whole (D-11).

**Writes.** A single writer path inside the one process. SQLite's single-writer limit is not a constraint at N-01 scale.

**Page cache.** Fetched pages are shared across investigations, subject to a freshness window (D-10). The window is a per-investigation setting with a global default, and "always refetch" is one of its values; that is how time-sensitive investigations (V5) get current pages. Within the window a URL is not refetched (V8). Claims, sources-as-evidence and everything else stay strictly per investigation. An investigation records which page version it used, so its evidence stays reproducible after the shared page is refreshed.

**Extraction reuse.** Claims extracted from a page inside an investigation are stored against that page version. A node that reruns after a restart reuses them rather than paying for extraction again (D-07).

**Report.** A written document stored with the investigation (D-16). It is stored as structured content in which every statement references the claims it rests on, so links to nodes and sources are data, not text conventions. Markdown export is generated from it and never contains settings or keys.

**Retention and deletion.** Nothing is pruned automatically (C-10). Deleting an investigation removes its events, state, evidence and trails, and removes page files no other investigation references. Disk usage is reported per investigation; a shared page counts towards every investigation that uses it, so the figures can sum to more than the total on disk (D-21).

**Tenancy.** None. One user, one database.

**Migration.** Greenfield; nothing to migrate. Schema changes after data exists are handled by versioned migrations plus rebuild-from-log for state tables. Event shapes are versioned from the first release, because old events must stay readable forever.

## 6. Interfaces and contracts

All interfaces are internal: the only consumer is Netgrip's own frontend.

**Queries (HTTP, request/response).** Investigation list, state snapshot of one investigation, node detail (claims, trail, raw material on demand), report, settings, disk usage.

**Plan review (D-17).** Creating an investigation does not start research. The engine first produces an initial plan — the root goal, extracted premises and the first decomposition — and shows it as a graph. The user steers it with free-text instructions; each instruction re-plans the graph, and the changes arrive over the live stream like any other event. Research starts only when the user approves the plan. Planning uses the same commands, events and re-plan mechanism as a running investigation; it is a phase of the lifecycle, not a separate subsystem.

**Commands (HTTP, request/response).** Every intervention in domain spec 4.9, plus create investigation, instruct the plan, approve the plan, resume or finish a Stopped investigation (D-18), export the report, and change settings. Each command carries a client-generated ID; a repeated ID is a no-op, so a retried request cannot apply an intervention twice. A command is acknowledged when recorded, not when it takes effect; the effect arrives as events.

**Live stream (server-sent events, one per open investigation).** Two kinds of message on one stream:

- *Durable events* — carry the log sequence number. The browser reconnects with the last number it saw and receives everything after it. No gap, no duplicate.
- *Ephemeral messages* — streamed model text and similar. No sequence number, not replayed after reconnect.

**Snapshot plus stream.** A browser that opens mid-run fetches the snapshot, which states the sequence number it is current to, then subscribes from that number.

**Stability.** Frontend and backend ship together, so the HTTP contract may change freely. The event schema is the exception: it is stored forever and must stay backward-readable (section 5).

## 7. External dependencies

| Dependency | Used for | Limits | Behavior when it's down |
|---|---|---|---|
| Model provider (OpenRouter first, any OpenAI-compatible endpoint) | All model calls in all tiers | Provider rate limits and account credit; shared across investigations by the global limiter | Retry with backoff for a bounded time, then pause the investigation with a visible reason (D-08) |
| Search API (Tavily) | Web search | Plan quota and rate limit | Same as above |
| Open web via headless browser | Fetching pages | Bot detection; own IP only (D-12); browser pool size (A-03) | Per-page: retry, escalate, then record as unobtainable and continue (W1–W3, E5). Never pauses the investigation |

Insufficient credit or an invalid key is not retried: the investigation pauses immediately with the reason.

## 8. Identity, access, security

- **Authentication:** none. The server binds to the loopback interface only (C-04). Binding elsewhere is not a supported configuration.
- **Secrets:** API keys are entered in the UI and stored in the database (D-13). They are write-only over the API: the browser can set or replace a key and see whether one is set, never read it back. Keys never appear in events, agent trails, logs or exports.
- **Sensitive data:** the user's prompts and research history. They leave the machine only as model and search requests.
- **Prompt injection:** handled structurally, as described in section 4 (P7).
- **Compliance regimes:** none apply.

## 9. Failure and recovery

| Failure | Intended behavior |
|---|---|
| Process killed or machine shut down | On start, each investigation returns to its recorded state. Running ones resume on their own. Nodes that were Running go back to Pending and rerun, reusing cached pages and extracted claims (D-07). Completed nodes are untouched. |
| Page fetch fails | Retry with increasing delay, escalate fetch method, then record unobtainable. Node continues (E5). |
| Page hangs or a browser operation exceeds its deadline | The session is closed and discarded; the fetch is retried under W1. |
| Browser tab or process crashes, or stops answering | The pool kills and replaces the browser; fetches that were on it are retried. Other investigations' fetches on healthy browsers are unaffected. |
| Fetch cancelled by pause, stop or shutdown | The session is closed before the step ends; no browser or page is left running. |
| Process killed with browsers open | Leftover browser processes and temporary profiles are removed at next startup. |
| Model or search provider outage | Bounded backoff, then system pause with reason. Resumes when the user resumes it. |
| Credit exhausted or key rejected | Immediate system pause with reason. |
| Money cap reached | Investigation pauses and asks the user: raise the cap, finish now, or stop (D-09). |
| Model returns malformed output | Retried within the step; repeated failure fails the step, and the node tries another route before failing (E5). |
| Duplicate command from the browser | Ignored by command ID. |
| Browser disconnects | No effect on the run. Reconnect resumes from the last sequence number. |
| Node fails | Recorded with reason. The orchestrator may try one different approach automatically, within the branch's remaining budget. A second failure stays Failed and visible; the user can re-run it (D-19). |
| Process killed during plan review | The plan as last shown is restored; nothing was running, so nothing reruns. |
| State tables disagree with the log | Should be impossible; if detected at startup, state is rebuilt from the log. |

A system-initiated pause is the same Paused state as a user pause, with a recorded reason and origin, so the UI can say why.

## 10. Operations

- **Environments:** one — the owner's machine. Development and use are the same environment.
- **Run:** the backend serves the API; in development the Vite dev server proxies to it; for normal use the backend serves the built frontend, so there is one thing to start.
- **Configuration:** non-secret settings (model tier assignments, presets, filters, caps, freshness window, pool sizes) live in the database and are edited in the UI. Secrets as in section 8.
- **Observability:** the event log is the primary record of what happened and why. A plain application log covers what the event log does not: adapter errors, retries, startup and recovery. Live spend per investigation and per node (M4) and disk usage per investigation are surfaced in the UI.
- **Backup:** copy the database file and the page directory while the process is stopped. Nothing more is designed.
- **Ownership:** the owner operates it.

## 11. Key decisions

- **D-01 — Python backend with uv; React frontend with Vite.**
  *Because:* C-01, C-02. *Rejected:* none considered. *Reversibility:* one-way.

- **D-02 — One process hosts the API and the engine, separated by a commands-in, events-out boundary.**
  *Because:* local, single user; recovery comes from the event log, not from process separation. *Rejected:* separate API and worker processes (needs inter-process messaging now for no present gain). *Reversibility:* two-way as long as nothing bypasses the boundary.

- **D-03 — Our own agent loop; no agent framework.**
  *Because:* pause and instruction at step boundaries (E4), per-step events, budgets and recovery are the core of the product, and a framework's execution model would own them. *Rejected:* LangGraph, PydanticAI or similar. *Reversibility:* one-way.

- **D-04 — The model client targets the generic OpenAI-compatible API.**
  *Because:* C-08; OpenRouter speaks it, and so do local runtimes the owner may want later. The loop assumes capable hosted models with tool calling and structured output for now. *Rejected:* a provider-specific SDK; supporting weak local models from day one. *Reversibility:* two-way behind the model client interface; supporting models without tool calling later means work inside the loop.

- **D-05 — Model, search and browser capacity are global pools shared by all investigations.**
  *Because:* C-06 and C-07; per-investigation limits would multiply load by five. *Rejected:* independent limits per investigation. *Reversibility:* one-way for the engine's shape.

- **D-06 — The append-only event log is the source of truth; state tables are updated in the same transaction and are rebuildable.**
  *Because:* L3 and P6 need a complete history; the live view and after-the-fact review read the same events. *Rejected:* state tables as truth with events as a side feed (history can drift); pure event sourcing with in-memory state only (slow restart, awkward queries). *Reversibility:* one-way.

- **D-07 — A node interrupted mid-run reruns from the start, reusing cached pages and the claims already extracted from them.**
  *Because:* avoids paying twice for the high-volume Fast tier work without checkpointing every agent step. *Rejected:* full rerun (wasteful); resume from last step (forces every step to be replayable). *Reversibility:* two-way; step-level resume can be added later because steps are already discrete.

- **D-08 — Provider outage: bounded backoff, then pause with a visible reason.**
  *Because:* N-02 and N-05; unattended runs must not fail or burn money overnight. *Rejected:* retry forever; fail the nodes and carry on. *Reversibility:* two-way.

- **D-09 — A hard money cap per investigation; reaching it pauses and asks.**
  *Because:* run length is unpredictable (N-02), so the effort budget alone does not bound spend. *Rejected:* auto "finish now" at the cap; no cap. *Reversibility:* two-way.

- **D-10 — Fetched pages are shared across investigations within a freshness window; evidence is per investigation.**
  *Because:* parallel investigations on related topics refetch the same pages; sharing claims would carry stale or contaminated conclusions between runs. Resolves domain open question 5. *Rejected:* full isolation; shared claims. *Reversibility:* one-way once investigations reference shared pages.

- **D-11 — Activity lines are persisted; streamed model text is shown live but not stored token by token.**
  *Because:* visible research without bloating the log. *Rejected:* activity lines only; persisting every token. *Reversibility:* two-way.

- **D-12 — Bot-detection avoidance stops at a hardened browser on the owner's own IP.**
  *Because:* proxies and CAPTCHA services add cost, secrets and dependencies; W3 already defines what happens to a blocked page. *Rejected:* paid proxies; CAPTCHA solving. *Reversibility:* two-way behind the fetcher interface.

- **D-13 — API keys are entered in the UI and stored in the database.**
  *Because:* owner's choice, for convenience. *Rejected:* a local environment file (recommended during the interview; keeps secrets out of the research data file). *Reversibility:* two-way. Consequence: the database file is a secret; see R-04.

- **D-14 — SQLite for structured data, page bodies as files; server-sent events for the live stream, HTTP for commands.**
  *Because:* single process, single user, N-01 scale; one-directional push with resumption is exactly what server-sent events provide. *Rejected:* a database server; WebSocket. *Reversibility:* storage engine is one-way after real data exists; transport is two-way.

- **D-15 — Engine tests run against a fake model client and recorded web fixtures; live runs are manual.**
  *Because:* graph logic, recovery, interventions and budgets must be testable deterministically and for free. *Rejected:* live-only testing; a scored evaluation set (deferred, section 12). *Reversibility:* two-way.

- **D-16 — The report is a written document stored with the investigation, with every statement linked to claims, nodes and sources; viewed in the app, exportable as Markdown.**
  *Because:* owner's choice; the simplest shape that satisfies R1. Resolves domain open question 1. *Rejected:* an additional annotated-graph view; verdict plus evidence list only. *Reversibility:* two-way; further views can be added over the same stored structure.

- **D-17 — The initial plan is always reviewed. The user sees the first decomposition, steers it by instruction with the graph updating live, and research starts on approval.**
  *Because:* owner's choice. Resolves domain open question 3. *Rejected:* starting immediately (recommended during the interview); an optional setting. *Reversibility:* two-way. Consequences: the investigation lifecycle gains a planning phase between Draft and Running; instructing the root is allowed during planning; an investigation cannot run fully unattended from creation.

- **D-18 — A Stopped investigation can be resumed or finished into a report later.**
  *Because:* everything is kept anyway; making Stopped final only removes options. Resolves domain open question 4. *Rejected:* finish-only; final. *Reversibility:* two-way.

- **D-19 — A failed node gets one automatic retry with a different approach, within the branch budget; after that it stays Failed until the user acts.**
  *Because:* unattended runs (N-02) should not stall on one node, and the budget bounds the cost. Resolves domain open question 7. *Rejected:* always wait for the user; unlimited orchestrator discretion. *Reversibility:* two-way.

- **D-20 — Effort budgets ship as placeholder values editable in settings, tuned after the first live runs.**
  *Because:* any value chosen now is a guess. Partly resolves domain open question 2. *Reversibility:* two-way.

- **D-21 — A shared page counts towards the disk usage of every investigation that uses it.**
  *Because:* owner's choice; each figure answers "how big is this investigation". *Rejected:* first fetcher only; separate own and shared figures. *Reversibility:* two-way.

- **D-22 — Browsers are owned by one pool with strict cleanup: a deadline on every operation, guaranteed release on every exit path, discard after any fault, periodic recycling, and removal of leftovers at startup.**
  *Because:* owner's requirement; browser control fails transiently as a matter of course, runs last for hours (N-02), and memory is limited (C-07), so a leaked browser or tab is a slow failure of the whole machine. *Rejected:* letting each node manage its own browser (no single place to enforce cleanup); reusing sessions after errors (carries broken state forward). *Reversibility:* two-way behind the fetcher interface, but the single-owner rule is what the rest relies on.

## 12. Deferred decisions

- **Hosting and remote access.** Seam: the loopback-only bind and the absence of auth are isolated in the API layer.
- **Engine in its own process.** Seam: the commands-in, events-out boundary (D-02).
- **Local models.** Seam: the model client interface (D-04).
- **Step-level resume of interrupted nodes.** Seam: discrete steps (D-07).
- **Answer-quality evaluation set.** Worth adding once prompts are being tuned; the fake model client and fixtures (D-15) are the base it builds on.
- **Web framework, graph rendering library, content extraction library.** Build-time choices; none shapes the architecture.

## 13. Risks

- **R-01** — Cost tracking depends on what the provider reports. A generic OpenAI-compatible endpoint may return token counts without prices, which makes the money cap (D-09) inaccurate.
  *Mitigation:* a per-model price table in settings as fallback; models without a known price are flagged before a run starts. *Early signal:* live spend disagrees with the provider's dashboard.

- **R-02** — Agent quality is not covered by tests (D-15). The engine can be correct while answers are poor.
  *Mitigation:* manual live runs; the deferred evaluation set. *Early signal:* prompt changes made without any way to compare before and after.

- **R-03** — Browser memory on a 16 GB machine with five investigations running.
  *Mitigation:* the global browser pool (D-05) with a conservative size (A-03); strict cleanup and recycling (D-22). *Early signal:* swapping or browser crashes under parallel runs.

- **R-04** — API keys sit in the same database file as research data (D-13). Copying or sharing that file leaks them.
  *Mitigation:* keys in a dedicated table, write-only over the API, excluded from any export. *Early signal:* any feature that exports or shares an investigation.

- **R-05** — The event schema is permanent. An early careless event shape must be supported forever.
  *Mitigation:* versioned events from the first release. *Early signal:* state rebuild needing special cases.

- **R-06** — Hardened browsing on one home IP may get that IP rate-limited or blocked by some sites.
  *Mitigation:* per-domain politeness limits in the fetcher. *Early signal:* rising unobtainable-page counts for one domain.

## 14. Open questions

Q-01 to Q-07 from the first draft were settled on 2026-11-12 and are now D-10 (freshness setting) and D-16 to D-21. Remaining:

- **Q-08** — Can the user instruct the root node after research has started, re-planning the whole investigation (domain open question 8)? D-17 allows it during planning only. Affects command rules, not architecture.
- **Q-09** — Actual effort budget values (D-20). Needs live runs. Blocks nothing structural.

## 15. Assumptions

Asserted here, not confirmed by the owner.

- **A-01** — "Vite" for the frontend build. The owner's message was cut off at "white for the".
- **A-02** — The page freshness window is configurable, with a default on the order of a day. Not discussed.
- **A-03** — The browser pool is sized conservatively for 16 GB, on the order of 6–8 concurrent pages in total. Not measured; revisit on first parallel runs (R-03).
- **A-04** — "Bounded" backoff before a system pause means minutes, not hours. Not discussed.
- **A-05** — The backend serves the built frontend for normal use, so there is a single process to start. Not discussed.
- **A-06** — SQLite and server-sent events (D-14) were stated to the owner as my choices and not objected to; they were not explicitly approved.
- **A-07** — Keys are stored unencrypted. Encrypting them at rest on a single-user local machine was not discussed.

- **A-08** — Plan review does no web research: planning produces the root goal, premises and first decomposition from the prompt alone, and premise checks appear in the plan as nodes that run after approval. Not discussed. Planning still costs model calls, which count towards the money cap.

- **A-09** — The specific browser cleanup mechanisms in D-22 (deadlines, discard after fault, periodic recycling, startup sweep) are my reading of "robust with strict cleanups". The requirement is the owner's; the list is mine. Deadline lengths and the recycling interval are not chosen.

## 16. Out of scope

- Hosting, deployment, remote or LAN access.
- Multiple users, accounts, authentication, sharing.
- Paid proxies and CAPTCHA solving.
- Sources other than the open web.
- Automatic pruning of stored data.
- Agent prompt design, node kinds, claim statuses and other domain rules — those live in the domain spec.
