# ScreenControlBoard

The investigation detail screen while research runs: one header and three panes that show the same nodes by time, by structure and one at a time. This is where the user watches and steers.

**Regions**

1. **Header** (60px). Back; StatusPill with effort, preset, run time and running count; a `danger` pill when a premise has been refuted; the prompt as `title`; three BudgetMeters (Spend, Nodes, Depth); RunControls; an overflow with Export events, Open report and Delete investigation.
2. **Left pane, 284px: ExecutionOrder.** Now, Next, Done, Not running. Answers "what is happening, what comes after, what already happened".
3. **Centre: GraphCanvas** under a 40px toolbar (node counts; Fit, Collapse completed, Show excluded, Follow active), with the **EventLog** docked below. The log collapses to its head row.
4. **Right pane, 364px: the inspector** for the selected node. Top: kind, id, depth, StatusPill, question, the node's "Why", and the four most used NodeActions. Tabs: Overview, Claims, Brief, Trail, Instructions. The InstructionComposer is pinned to the bottom and always aims at the selected node.

**Rules**

- One selection, three panes. Clicking a node, a queue row or a log row selects the same node everywhere. With nothing selected, the inspector shows the root.
- Pink means the user, cyan means agents. On this screen `steer` appears only on the composer, the user's instructions, the user's log rows and node marks. `live` appears only on running or waiting work.
- The screen never guesses state. Controls show `is-sent` wording until the confirming event arrives over the stream; the toolbar's "current to #0419" is the proof of freshness.
- A SystemPause banner, when present, sits between the header and the panes and pushes them down.
- "Run only this branch" replaces the header's mono line with "Running only D2" and a "Run everything" button; nodes outside the branch dim to `ink-faint` text but keep their state.
- When the stream disconnects, the header pill gains "· reconnecting" in `warn`, live glyphs stop pulsing, and controls stay usable (commands queue with their ids).
- Paused: no node pulses, Now is empty, the pill is `warn` with its origin, and the header's Pause becomes the steer button Resume.
- Synthesising: the graph is read-only, the left pane shows "Writing the report from 61 claims", and the composer is locked.
- Completed or Stopped: the same board opens read-only as history, with "Open report" as the header's main button.

**Keyboard.** `↑ ↓` move through the queue; `← →` parent and first child in the graph; `I` instruct; `D` go deeper; `F` run only this branch; `Space` pause or resume branch; `X` ignore or restore; `R` re-run; `L` toggle the log; `.` node menu; `Esc` clear selection.

**Narrow widths.** Below 1180px the inspector becomes an overlay sheet over the graph; below 900px the left pane becomes a tab beside "Graph" and "Log". The composer stays reachable in every layout.
