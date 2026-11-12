# ExecutionOrder

The left pane of the board: the same nodes as the graph, ordered by time instead of by structure. Four sections, always in this order: **Now**, **Next**, **Done**, **Not running**. Rows are `ng-qrow` under sticky `ng-queue__head` section heads.

You provide the node list with status, activity, wait reason, verdict summary and timestamps. Order within Next comes from the scheduler, not from the UI.

| Section | Holds | Row meta | Side |
|---|---|---|---|
| Now | Running nodes | the ActivityLine | time in this run |
| Next | Pending and Proposed nodes, and coordinators waiting to aggregate, in the order they will start | why it has not started: "waits for D3 (dependency)", "waits for a free slot", "awaiting the orchestrator" | position |
| Done | Completed and Failed nodes, newest first | verdict summary and confidence, or the failure reason | time finished |
| Not running | Ignored, Superseded, Rejected and Paused nodes | who excluded it and a Restore link | none |

- The Now head shows the slots in use: "4 running · 6 slots". When the investigation is paused, Now is empty and the head reads "Nothing runs while paused".
- With "Run only this branch" on, nodes outside the branch move to Next with "waits: you are running only D2".
- A refuted premise in Done uses the `danger` cross, because the finding matters more than the fact that the node completed.
- Selecting a row selects the node in the graph and the inspector, and the graph pans to it. Selection is shared by all three panes.
- Next is the place to answer "what happens after this?". Never hide it, even when empty: "Nothing queued. The orchestrator is deciding."
