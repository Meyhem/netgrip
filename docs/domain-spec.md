# Netgrip — Domain Specification

**Status:** draft v2 · 2026-11-12 (v2 records the answers given while writing the [technical specification](tech-spec-netgrip.md))
**Scope:** the domain only — concepts, rules, lifecycles and vocabulary. Architecture, frameworks, storage and API design are deliberately out of scope and will be covered by a separate technical design. Technology choices the owner has already made are listed in [Appendix A](#appendix-a--technical-decisions-already-made) so they are not lost.

**How to read the markers**

- No marker — decided or explicitly accepted by the project owner.
- **(proposed)** — suggested during brainstorming, not yet explicitly confirmed.
- **(open)** — undecided; listed again in [Open questions](#11-open-questions).

---

## 1. Purpose

Netgrip is a deep web research system. A user states a problem, a question, or a claim. The system investigates it on the open web and returns a **high-confidence, evidence-backed answer**.

The investigation is carried out by AI agents organised as a **graph of tasks** that grows while it runs: analysing one problem may create sub-problems, each explored by an independent agent. A single orchestrator steers the whole run. The user watches the graph form in real time, sees what every node is doing, and can intervene at any moment.

### What makes it distinct

1. **The research is visible.** The graph, the live activity of each node, and each node's result are shown as they happen. It is not a black box that returns text after ten minutes.
2. **The user steers it.** The user can pause, stop, redirect, prune and reshape the investigation while it runs.
3. **It verifies rather than agrees.** What the user asserts is treated as a hypothesis. If the user is wrong, the result says so.
4. **Confidence is earned from evidence.** Conclusions are built from sourced, cross-checked claims, not from summaries of summaries.

### Primary use cases

- **Fact-checking** a claim or a premise ("Nvidia has a problem with its CEO").
- **Deep analysis** of a topic: first broadly (divergent — which lines of thought exist?), then deeply (convergent — each line investigated in detail).

---

## 2. Core principles

| # | Principle |
|---|-----------|
| P1 | **User claims are hypotheses, not facts.** A statement in the user's prompt never biases an agent's conclusion. Every premise is checked, and a wrong premise is reported back explicitly. |
| P2 | **User instructions steer what is investigated, never what is concluded.** The user may narrow, redirect or prune the research; the user cannot dictate a finding. Anything the user excluded is disclosed in the report. |
| P3 | **Every conclusion traces to sources.** A statement in the final report can be followed back to the claims, the node, and the web sources it came from. |
| P4 | **Uncertainty is stated, not hidden.** What could not be verified is reported as such. |
| P5 | **The main goal is never lost.** Every agent, at any depth, works with the user's original question in front of it. |
| P6 | **Nothing is lost on interruption.** Shutting the system down mid-run loses no completed work; the run recovers and continues. |
| P7 | **Web content is data, never instructions.** Text found on a web page cannot direct an agent's behaviour. |
| P8 | **Work that can run in parallel runs in parallel.** Only real dependencies force ordering. |
| P9 | **User actions are reversible wherever possible.** Ignoring or reshaping a branch greys work out; it does not destroy it. |

---

## 3. Glossary

| Term | Meaning |
|------|---------|
| **Investigation** | One complete research run for one user prompt: its graph, evidence, settings and report. |
| **Prompt** | The user's original problem statement, kept verbatim for the whole investigation. |
| **Root goal** | The question the investigation must answer, derived from the prompt. Immutable. |
| **Premise** | A factual assumption contained in the prompt, extracted and verified as a hypothesis. |
| **Task graph** | The growing graph of nodes and edges that represents the investigation. |
| **Node** | One unit of research with its own question, executed by one agent. |
| **Branch** | A node together with all its descendants. |
| **Brief** | The input package a node receives: root goal, path, own task, what is already known. |
| **Path** | The chain of ancestors' objectives explaining why a node exists. |
| **Orchestrator** | The single global decision-maker for the investigation. |
| **Coordinator** | A node that has children: it decomposes its question and later aggregates their results. |
| **Activity** | What a running node is doing right now (searching, reading, reasoning…). |
| **Verdict** | A node's short conclusion with a confidence level. |
| **Claim** | One atomic, checkable statement supported by one or more sources. |
| **Source** | A web document used as evidence. |
| **Evidence store** | The investigation-wide collection of sources and claims, shared by all nodes. |
| **Effort** | The user's low / medium / high setting that determines the investigation's budget. |
| **Budget** | The limits an investigation, branch or node must stay within. |
| **Model tier** | A class of AI model assigned to a kind of work (Strong / Standard / Fast). |
| **Intervention** | Any action the user takes on a running investigation or node. |
| **Instruction** | A free-text intervention attached to a node that changes how its branch proceeds. |
| **Re-plan** | A coordinator revising its children in response to an instruction. |
| **Report** | The final output of an investigation. |

---

## 4. Domains

### 4.1 Investigation

The top-level aggregate. Created from a prompt; owns everything else.

**Holds**

- the prompt (verbatim) and the root goal;
- the extracted premises and their verification outcomes;
- settings chosen by the user: effort, model tier assignments, source filters **(proposed)**;
- the budget and how much of it is spent;
- the task graph, the evidence store, the event history, and eventually the report.

**Rules**

- I1. The prompt and root goal never change during an investigation.
- I2. Premise verification is part of every investigation and happens first (see [4.5](#45-evidence)).
- I3. An investigation belongs to a single user. There is one user of the system **(proposed — see non-goals)**.
- I4. Finished investigations are kept as history and can be reopened. A Stopped investigation can be resumed, or finished into a report, at any later time. A follow-up question may extend an existing graph instead of starting from zero **(proposed)**.
- I5. No research starts before the user has approved the initial plan (see [4.9](#49-user-control)).
- I6. An investigation's stored material is kept until the user deletes the investigation. The user can see how much disk space each investigation occupies.

Lifecycle: see [6.1](#61-investigation-lifecycle).

### 4.2 Task graph

**Node** — one research question plus everything known about its execution.

A node has:

- a **question** (its own task) and a one-line **justification**: how answering it helps the root goal;
- a **scope fence**: what is explicitly out of scope, and what "done" looks like;
- a **kind** **(proposed)**:
  - *Premise check* — verifies an assumption from the prompt;
  - *Divergent* — explores breadth, identifies lines of thought;
  - *Deep-dive* — investigates one line in detail;
  - *Verification* — independently re-checks important or contested claims;
  - *Synthesis* — combines results (the root's final step);
- a budget, a brief, a lifecycle status, a live activity, and — once finished — an output.

**Edges** — two kinds:

- **Decomposition** (parent → child): the child exists because the parent split its question.
- **Dependency** (A → B): B cannot start until A is complete, and B's brief includes A's results.

**Rules**

- G1. The graph is acyclic.
- G2. A node becomes eligible to run as soon as all nodes it depends on are complete. Eligible nodes run concurrently, up to the parallelism allowed by the budget.
- G3. A coordinator finishes only after its included children have finished and it has aggregated them.
- G4. Every node carries a justification visible to the user. A node without a convincing justification is not created.
- G5. Nodes are never deleted. Work that is no longer wanted is marked, not removed (see inclusion, [6.2](#62-node-lifecycle)).

### 4.3 Orchestration

Two levels of decision-making, not a cascade of sub-orchestrators.

**Coordinator (any node with children)** — local authority over its own branch:

- decides whether its question should be answered directly or split;
- *proposes* children, each with question, justification and scope fence;
- aggregates the children's results into its own verdict;
- re-plans its children when the user instructs it to.

**Orchestrator (one per investigation)** — global authority. Only the orchestrator sees the whole graph. It:

- approves or rejects proposed nodes;
- allocates budget across branches and decides priorities;
- detects duplicate or overlapping work across branches and links to the existing node instead of creating a second one **(proposed)**;
- decides when to go deeper, when to split wider, and when the investigation has enough to conclude;
- triggers final synthesis.

**What the orchestrator works from:** the graph skeleton and every node's verdict. It pulls a node's claims only when it needs the detail. It never receives raw page content.

**Rules**

- O1. A proposed node is rejected if its justification is weak, if it duplicates existing work, or if the budget does not allow it.
- O2. Budget shrinks with depth: deeper nodes receive smaller budgets, so a tangent exhausts itself.
- O3. When the budget is exhausted, no new nodes are created; running nodes finish; the investigation proceeds to synthesis and the report states that it was cut short **(proposed)**.
- O4. User interventions always take precedence over the orchestrator's own plan.
- O5. When a node fails, the orchestrator may try one different approach on its own, within the branch's remaining budget. If that also fails, the node stays Failed and visible until the user acts on it.

### 4.4 Node execution

**The brief** — what every node receives, at every depth:

1. **Root goal** — the user's original question, verbatim.
2. **Path** — one line per ancestor: why this node exists.
3. **Own task** — the question, the scope fence, the definition of done, the budget.
4. **What is already known** — relevant claims from the evidence store (so they are not re-researched), results of nodes it depends on, and user instructions inherited from ancestors.

A node does **not** receive the whole graph or its siblings' outputs.

**Activity** — the live status shown on the node while it runs:

| Activity | Meaning |
|----------|---------|
| Planning | deciding how to approach the question |
| Searching | running a web search |
| Reading | fetching and reading a page |
| Extracting | pulling claims out of page content |
| Reasoning | weighing what was found |
| Aggregating | combining children's results |
| Waiting on children | children are still running |
| Retrying (n of m) | a transient failure is being retried |

The activity carries enough detail to be meaningful (which query, which page).

**Output** — three layers:

| Layer | Content | Who uses it |
|-------|---------|-------------|
| **1 · Verdict** | a few sentences: what was found, with what confidence | orchestrator (always); shown on the node |
| **2 · Claims** | structured claims with sources, confidence, contradictions; open questions; proposed follow-up nodes | the evidence store; orchestrator on demand; final synthesis |
| **3 · Raw material** | fetched pages, the full trail of the agent's work | stored and retrievable; never passed along automatically |

**Rules**

- E1. A node's result is shown on the node as soon as it exists, before the orchestrator acts on it.
- E2. Claims go directly into the evidence store. They are not re-told up the chain of parents; a parent refers to its children's claims rather than rewriting them.
- E3. A node's results are checked for relevance to the root goal on return. Off-topic findings are flagged and kept out of synthesis.
- E4. A user instruction given to a running node takes effect at the node's next step, not in the middle of a step.
- E5. The failure of one page or one search never fails the node. A node fails only when it cannot make progress by any route.

### 4.5 Evidence

The investigation-wide, shared body of knowledge. This is where confidence comes from.

**Source** — a web document: where it is, when it was retrieved, when it was published (if known), and a credibility class **(proposed)**:

- *Primary* — official statements, filings, original data;
- *Reputable secondary* — established news and reference outlets;
- *Weak* — blogs, forums, anonymous or unattributed content.

**Claim** — one atomic, checkable statement. It records the sources supporting it, the sources contradicting it, the node that produced it, and a status **(proposed)**:

| Status | Meaning |
|--------|---------|
| Confirmed | supported by enough independent sources for the chosen effort level |
| Supported | supported, but below the confirmation threshold |
| Unverified | a single or weak source only |
| Contested | credible sources disagree |
| Refuted | credible evidence shows it is false |

**Premise verification** — premises extracted from the prompt are claims like any other, with one addition: each must end with an explicit outcome (confirmed / refuted / could not be verified), and every refuted premise must be surfaced in the report.

**Rules**

- V1. No claim exists without at least one source.
- V2. Independence is judged by origin, not by address: several articles repeating one wire report count as one source **(proposed)**.
- V3. Contradictions between claims — including claims from different branches — are detected and recorded, never silently resolved.
- V4. The confirmation threshold depends on effort: lower effort means a lower bar, and the report says which bar was used.
- V5. For time-sensitive questions, the publication date of a source matters; stale sources must not be presented as current.
- V6. The final synthesis is built from the evidence store, not from node summaries.
- V7. Verification of important claims is ideally done by a different model than the one that produced them, to avoid repeating the same mistake **(proposed)**.
- V8. A page fetched once in an investigation is reused by every node that needs it.
- V9. Fetched pages may also be reused by other investigations while they are fresh enough. How fresh is a setting of each investigation, and "always fetch again" is one of its values — the choice for time-sensitive questions (V5). Claims are never shared between investigations: each investigation builds its own evidence.

### 4.6 Web acquisition

How information enters the system: **searching** the web and **fetching** pages, turning them into clean readable text.

**Rules**

- W1. Transient failures (timeouts, crashes, unresponsive pages, temporary blocks) are retried with increasing delay, up to a limit. The retry is visible on the node.
- W2. Fetching escalates: a simple fetch first, then a full browser, then a browser hardened against bot detection. If all fail, the page is given up and the agent looks for another source **(proposed order)**.
- W3. A page that cannot be obtained is recorded as unobtainable; it is not silently skipped.
- W4. The user may exclude or prefer domains ("no Reddit", "primary sources only") **(proposed)**.
- W5. Fetched content is treated as untrusted data (P7).

### 4.7 Model configuration

Work is divided into tiers so that expensive models are used only where they matter.

| Tier | Used for | Load profile |
|------|----------|--------------|
| **Strong** | orchestrator, final synthesis, judging contradictions | few calls, decisive for quality |
| **Standard** | the agent inside a node: plans searches, picks sources, reasons about findings | moderate call volume |
| **Fast** | reading pages, extracting claims, relevance filtering, de-duplication, status lines | very high text volume, simple work |
| **Verifier** *(optional slot)* **(proposed)** | independent re-checking of claims | defaults to the Strong tier; ideally a different model family |

**Rules**

- M1. The user chooses which model fills each tier.
- M2. Presets exist — Economy / Balanced / Maximum quality — and any tier can be overridden individually **(proposed)**.
- M3. To choose knowingly, the user sees for each tier what it does and roughly what share of the cost it accounts for, and gets a cost estimate for the run before starting it **(proposed)**.
- M4. Spend is tracked live, for the investigation and per node **(proposed)**.
- M5. The system is not tied to a single AI provider.

### 4.8 Effort and budget

**Effort** is one user-facing choice — Low / Medium / High — that trades speed and cost against depth and rigour.

Effort determines the **budget**:

- maximum graph depth;
- maximum number of nodes;
- number of sources consulted per node;
- degree of parallelism;
- verification strictness (how many independent sources confirm a claim).

Concrete values per level are **(open)**.

**Rules**

- B1. Budget is allocated by the orchestrator to branches and nodes, shrinking with depth (O2).
- B2. A user's "go deeper here" grants a branch additional budget.
- B3. A low-effort result must be honest about being one: the report states the effort level and the evidence bar used.
- B4. Each investigation has a spending limit in money, separate from the effort budget. Reaching it pauses the investigation and asks the user what to do: raise the limit, finish now, or stop.
- B5. The planning that precedes approval counts towards the spending limit.

### 4.9 User control

The user has robust control over a running investigation.

**Investigation-level interventions**

| Action | Effect |
|--------|--------|
| **Instruct the plan** | free-text guidance that reshapes the initial plan before any research starts |
| **Approve plan** | accepts the plan; research begins |
| **Pause** | no new work starts; the investigation can be resumed exactly where it was |
| **Resume** | continues a paused investigation |
| **Stop** | ends execution without producing a report; everything gathered is kept, and the investigation can later be resumed or finished into a report |
| **Finish now** | stops exploring and synthesises a report from what exists so far **(proposed)** |

**Node-level interventions**

| Action | Effect |
|--------|--------|
| **Ignore branch** | the branch stops, and its results are excluded from synthesis. Reversible. |
| **Restore branch** | undoes an ignore |
| **Pause / resume branch** | suspends or continues one branch only |
| **Run only this branch** | execution continues in this branch while the rest of the graph waits |
| **Add instruction** | free-text guidance for the node; inherited by its whole branch |
| **Go deeper** | grants the branch more budget **(proposed)** |
| **Re-run node** | discards the node's result and executes it again **(proposed)** |

**Plan review** — every investigation begins with a plan the user approves.

1. From the prompt, the system derives the root goal, the premises to check, and a first decomposition, and shows them as a graph.
2. The user steers the plan with free-text instructions. Each instruction re-plans the graph, and the user sees the graph change as a result.
3. When the user approves the plan, research begins. Premise checks are part of the plan and run first (I2).

No web research happens during plan review **(proposed)**. After approval, the investigation is steered with the interventions below.

**Re-planning by instruction** — the user can change the *shape* of the graph with a prompt. When an instruction is added to a node that already has children:

1. the coordinator compares its existing children with the instruction;
2. children that still fit are kept, **including results they already produced**;
3. children that no longer fit are stopped and marked superseded (greyed out, restorable);
4. new children are proposed to satisfy the instruction;
5. the instruction is inherited by every node in the branch.

*Example:* a node has five children exploring five websites. The user instructs it to concentrate on one specific site. The children for the other four are superseded, and new children are created to explore that one site in more detail.

**Rules**

- U1. An instruction applies to the node it is given to and to all its descendants.
- U2. Instructions change scope and direction only; they cannot set a conclusion (P2).
- U3. Ignored and superseded work stays visible, greyed out, and can be restored (P9).
- U4. Everything the user excluded is disclosed in the report.
- U5. A re-plan takes effect immediately, without a confirmation step, because it is reversible **(proposed)**.
- U6. During plan review the user may instruct the root node, re-planning the whole investigation. Whether this is also allowed once research has started is **(open)**.

### 4.10 Live view and history

Everything that happens in an investigation is a recorded **event**: a node proposed, approved, started; an activity changed; a claim added; a user intervention; a budget change.

**Rules**

- L1. The user sees the graph update in real time: nodes appearing, what is executing, each node's current activity, and each node's result once it has one.
- L2. Every node shows its justification — its "why" — so that drift from the root goal is visible to the user.
- L3. The event history is complete enough to restore the investigation's state after an interruption (P6) and to review afterwards how a conclusion was reached.
- L4. Large graphs stay readable: branches can be collapsed, active work is highlighted, and a node's detail is available on demand **(proposed)**.

### 4.11 Report

The final output of an investigation, synthesised from the evidence store. It is a written document kept with the investigation, read inside the system, and exportable as a text document. Proposed contents:

- **The answer** to the root goal, with an overall confidence.
- **Where you were wrong** — premises from the prompt that were refuted, with the evidence. Required whenever any premise is refuted (P1).
- **Key findings** — the claims the answer rests on, each with status and sources.
- **What could not be verified** — unverified and contested claims (P4).
- **Limits of this investigation** — effort level and evidence bar, anything cut short by budget, branches the user ignored (U4), pages that could not be obtained.

**Rules**

- R1. Every statement in the report links back to its claims, the nodes that produced them, and their sources (P3).
- R2. The report never states as fact something whose claim status is below Confirmed without saying so.

---

## 5. Cross-cutting concern: staying on topic

Agents drifting away from the main idea is a central risk. It cannot be eliminated, but it is made cheap and visible by five mechanisms working together:

1. **Anchor** — the root goal is in every brief (P5).
2. **Gate on creation** — every proposed node needs a justification tied to the root goal; weak ones are rejected (O1, G4).
3. **Gate on return** — results are checked for relevance; off-topic findings do not reach synthesis (E3).
4. **Shrinking budget** — a tangent runs out of budget by itself (O2).
5. **Visibility** — the user sees each node's "why" and can prune (L2, 4.9).

---

## 6. Lifecycles

### 6.1 Investigation lifecycle

```
Draft ──▶ Planning ──approve plan──▶ Running ◀──resume── Paused
                                      │  └────pause────────▲
                                      │
                                      ├──(orchestrator concludes / budget exhausted / "finish now")──▶ Synthesising ──▶ Completed
                                      │
                                      └──stop──▶ Stopped ──resume──▶ Running
                                                    └──finish──▶ Synthesising
```

- **Draft** — prompt and settings entered, nothing executed yet.
- **Planning** — the initial plan is shown and the user is steering it; no research is running.
- **Running** — nodes are executing.
- **Paused** — suspended and resumable. Either the user paused it, or the system did: because the spending limit was reached (B4), or because a service the investigation depends on stayed unavailable. A system pause states its reason.
- **Synthesising** — exploration has ended; the report is being built.
- **Completed** — the report exists.
- **Stopped** — ended by the user without a report; gathered material is kept. It can be resumed, or finished into a report, later.

**Interruption** (the system is shut down or crashes) is not a state. On restart the investigation returns to the state it was in and, if it was Running, continues on its own.

An interruption during Planning restores the plan as the user last saw it. Whether a Completed investigation can be extended by a follow-up question is **(proposed — see I4)**.

### 6.2 Node lifecycle

A node has two independent dimensions.

**Execution status**

```
Proposed ──approved──▶ Pending ──dependencies met──▶ Running ──▶ Completed
    │                     ▲                            │  ▲
    └──rejected──▶ Rejected                            │  └── Waiting on children
                          │                            ├──▶ Failed
                          └────────── Paused ◀─────────┘
```

- **Proposed** — suggested by a coordinator, awaiting the orchestrator.
- **Rejected** — declined by the orchestrator (with a reason).
- **Pending** — approved, waiting for dependencies or for a free slot.
- **Running** — executing; has a live activity.
- **Waiting on children** — decomposed; will aggregate when children finish.
- **Paused** — suspended by the user.
- **Completed** — has an output.
- **Failed** — could not make progress by any route, including the orchestrator's one automatic retry (O5). The user can re-run it.

**Inclusion**

- **Included** — counts towards the investigation's result (default).
- **Ignored** — excluded by the user; reversible.
- **Superseded** — replaced during a re-plan; reversible.

A node that is not Included does not execute, and its claims are not used in synthesis. Changing inclusion applies to the whole branch.

**Recovery rule:** after an interruption, Completed nodes stay Completed; nodes that were Running return to Pending and are executed again; already-fetched pages, and the claims already extracted from them, are reused (V8).

---

## 7. Key scenarios

**S1 · Fact-check with a wrong premise.** The user asks for an analysis of "Nvidia's problem with its CEO". The premise "Nvidia has a problem with its CEO" is extracted and checked first. The investigation proceeds on what the evidence shows, not on what the user assumed. If the premise is false or outdated, the report's "Where you were wrong" section says so, with sources.

**S2 · Divergent then convergent.** A divergent node maps the lines of thought around the question. Each approved line becomes a deep-dive node running in parallel. Deep-dives may split further. Each node's verdict appears on the node as it completes; the orchestrator decides where to go deeper and when there is enough to conclude.

**S3 · Pruning.** The user sees a branch that is irrelevant and ignores it. The branch stops, greys out, and its findings are excluded. The report lists it among excluded branches.

**S4 · Reshaping by instruction.** The user instructs a coordinator to specialise. Fitting children are kept with their results, unfitting ones are superseded, new ones are created (see 4.9).

**S5 · Focus on one branch.** The user chooses "run only this branch". The rest of the graph waits while that branch continues.

**S6 · Unreliable page.** A page times out. The node shows "Retrying (2 of 3)". After the last attempt fails by every route, the page is recorded as unobtainable and the agent finds another source. The node does not fail.

**S7 · Shutdown mid-run.** The user closes the system while eight nodes are running. On restart, completed work is intact, the eight nodes run again using cached pages, and the investigation continues.

**S8 · Enough already.** The user chooses "finish now". Exploration stops and a report is synthesised from the evidence gathered so far, stating that it was ended early.

**S9 · Steering the plan.** The user enters a prompt and sees the proposed plan as a graph. They instruct it to leave out one line of inquiry and add another; the graph changes in front of them. They approve, and research begins.

**S10 · Unattended trouble.** Overnight, the model service stops responding. After a limited time of retrying, the investigation pauses and says why. In the morning the user resumes it and nothing has been lost or wasted.

---

## 8. Non-goals (for now)

- Hosting, deployment and remote access — the system runs on localhost / a home server.
- Multiple users, accounts, authentication, sharing **(proposed)**.
- Sources other than the open web (private documents, paid databases, logged-in content).
- Acting on findings — the system researches and reports; it does not take actions in the world.

---

## 9. Anti-goals

Outcomes that would make the project a failure even if it technically works:

- A report that confidently repeats the user's mistaken premise.
- A report whose statements cannot be traced to sources.
- A run that silently burns a large budget on tangents.
- A graph the user can watch but not influence.
- Losing an hour-long investigation because the process was restarted.

---

## 10. Unconfirmed proposals

Items marked **(proposed)** above, collected for review:

1. Node kinds (premise check, divergent, deep-dive, verification, synthesis).
2. Source credibility classes and claim statuses; independence judged by origin.
3. Orchestrator links to an existing node instead of duplicating work.
4. Behaviour when the budget runs out (finish running nodes, then synthesise).
5. Optional Verifier model slot; verification by a different model family.
6. Model presets, per-tier cost share, pre-run cost estimate, live cost meter.
7. Fetch escalation order.
8. Domain filters (exclude / prefer).
9. "Finish now", "Go deeper", "Re-run node" actions.
10. Re-plan applies immediately without confirmation.
11. Graph readability aids (collapse, highlight, detail on demand).
12. Report sections as listed in 4.11.
13. Single-user system; history and follow-up questions extending an existing graph.

---

## 11. Open questions

Numbers are kept from draft v1 so that references to them stay valid.

2. **Effort levels.** Concrete budget values for Low / Medium / High. To be set from experience with real runs; until then the values are provisional and adjustable by the user.
6. **Confidence scale.** Is confidence shown to the user as the claim statuses above, as a number, or both?
8. **Limits on re-planning.** The user can instruct the root node during plan review (U6). Can they also do so once research has started, effectively re-planning the entire investigation?

**Resolved in draft v2**

1. **Report shape** — a written document kept with the investigation and exportable (4.11). Its sections remain proposed.
3. **Plan review** — the user always reviews and steers the initial plan; research starts on approval (4.9, I5).
4. **Stop vs Pause** — a Stopped investigation can be resumed or finished later (I4, 6.1).
5. **Evidence across investigations** — fetched pages are reused while fresh; claims are not (V9).
7. **Failed nodes** — one automatic retry with a different approach, then the node waits for the user (O5).

---

## Appendix A — Technical decisions already made

Recorded for continuity; these are not domain rules.

- Backend in Python; frontend in React.
- AI models reached through OpenRouter initially; the design must stay open to other providers.
- Web search through a search API (Tavily was named).
- Page fetching through Playwright with bot-detection avoidance; Crawl4AI considered for extracting clean Markdown.
- Runs on localhost / the owner's home server; hosting is not a concern yet.
