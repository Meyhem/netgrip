# ScreenInvestigations

The home screen: every investigation as one table row, with its state, what it is doing or waiting for, and the one action that moves it forward.

**Regions**

1. Top bar: wordmark, Investigations / Settings, and the shared pools readout (`models 5/8 · search 1/4 · browsers 4/6 · today $3.12`).
2. Title row: `display` title, active count against the parallel limit, total disk, and the steer button "New investigation" (`N`).
3. Filter row: `ng-seg` with All, Needs you, Running, Finished; a search input.
4. Table: Prompt, State, Effort, Nodes, Spend, Disk, Run time, action.

**Row rules**

- Line 1 is the prompt, verbatim, in `heading`. Line 2 is `mono`: for Running, the count of running nodes and one live ActivityLine; for Plan review, what the plan holds; for Paused, the reason in `warn` and "Nothing is lost"; for Completed, refuted premises in `danger` and the answer's confidence.
- The action column holds exactly one button, chosen by state: Pause, Review plan, Resume, Open report, Finish into a report, Continue. Rows that wait for the user use `ng-btn--steer`.
- "Needs you" filters to Plan review and any Paused row. Its count is also the browser tab title: "(2) Netgrip".
- Sort: needs you first, then running, then by last activity.
- Row click opens the board (or the report for Completed). Delete lives in the row's overflow menu and in the board; it opens the app's only modal, on `scrim`, naming the prompt and the disk space that will be freed, with a `ng-btn--danger` "Delete investigation".
- At the parallel limit, "New investigation" stays enabled; the new one waits as a Draft and the title row says "5 active of 5 allowed".

**Empty state.** No table. The prompt box from ScreenNewInvestigation sits in its place under the line "Ask a question or state a claim. Netgrip will check it, including the parts you take for granted."
