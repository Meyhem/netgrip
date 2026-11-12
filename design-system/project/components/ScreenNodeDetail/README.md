# ScreenNodeDetail

The inspector's tabs and node states that the board screenshot does not show. Each panel here is the scrolling middle of the right pane; the node header above it and the composer below it stay as on ScreenControlBoard.

| Tab | Shows | Source |
|---|---|---|
| Overview | Now (ActivityLine, step number, time, sources read) while running; Verdict once it exists; claims so far; the branch's BudgetMeters; inherited instructions; open questions and proposed follow-ups | node state |
| Claims | filter tags by status; one ClaimCard per claim | evidence store |
| Brief | the Brief as the agent received it | stored brief |
| Trail | one `ng-well` per step: step number, time, activity verb, detail, link to the stored page | activity events; raw material on demand |
| Instructions | inherited instructions from the root down, then the node's own, oldest first | intervention events |

**Rules**

- The Trail's open step has a `live` border and shows streamed model text in italic `ink-faint` with a caret. A line under it says the text is live and not stored. Closed steps show only what was persisted.
- A `steer` rule in the Trail marks the step boundary at which an instruction was applied, so the user can see it did not interrupt a step.
- Retries appear in the Trail as their own steps in `warn`, with the fetch route used: simple fetch, full browser, hardened browser.
- "stored page" opens the page version this investigation used, as clean text, in a full-height sheet over the inspector. Page text is shown as inert text: no links are followed, no scripts or images load.
- A completed node's Overview leads with the Verdict, then open questions and the follow-ups it proposed with their orchestrator decision.
- A rejected node's Overview shows only the proposal, who proposed it and the orchestrator's reason. Its only action is Add instruction on the parent.
- An ignored or superseded node's Overview says who excluded it and when, what is kept, and offers Restore branch as the steer button.
- A failed node's Overview uses the Verdict component's failed state.
