# ScreenReport

The Completed state: the written report, read inside the app, with every statement traceable to claims, nodes and sources.

**Regions**

1. Header: Completed pill with effort, preset, run time, total spend and "ended early by you" when that applies; then Open the board, Export Markdown, and the steer button "Ask a follow-up".
2. Left, 220px: section links with counts ("Where you were wrong · 2" in `danger`), then the evidence bar in words and the totals.
3. Centre: the report in a 680px column (`ng-report`).
4. Right, 380px: the evidence pane for the citation that is open. It shows the ClaimCard, the path of nodes that produced it, and where else the report uses it. Closed by default; the report column then centres.

**Rules**

- Section order is fixed: The answer, Where you were wrong, Key findings, What could not be verified, Limits of this investigation. "Where you were wrong" is omitted only when no premise was refuted.
- The answer opens with one `display` sentence that answers the prompt directly, with an `ng-conf` readout above it. If the user's premise was wrong, that sentence says so.
- Every factual sentence ends in `ng-cite` chips. The open one is filled. Citing a premise uses its node id (P1).
- Findings below Confirmed carry their pill and an `ng-hedge` underline, and are worded as uncertain.
- Limits always states: effort and evidence bar, whether the run was cut short and by what (budget, spending limit, Finish now), pages that could not be obtained, and each exclusion or narrowing the user made, shown as Instruction blocks.
- "Open the board" opens ScreenControlBoard read-only with the same selection. "show on the board" in the evidence pane does the same for one node.
- Export Markdown produces the same sections with citations as footnotes. It contains no settings and no keys.
- "Ask a follow-up" opens the prompt box with this investigation attached; the new question extends the existing graph rather than starting again.
- While Synthesising, this screen shows the section headings with "Writing from 61 claims…" as an ActivityLine and no partial prose.
