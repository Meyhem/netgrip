# Steering the agent

How the user controls an investigation, and what the interface must show at each step. Components: RunControls, NodeActions, InstructionComposer, Instruction, SystemPause.

## Three ways to steer

| Way | Where | Scope | Component |
|---|---|---|---|
| Run controls | board header | the whole investigation | RunControls |
| Node actions | inspector action row, node menu, keyboard | one node and its descendants | NodeActions |
| Instructions | composer at the bottom of the inspector; under the graph in plan review | one node and its descendants, in words | InstructionComposer |

All three are `steer` pink where they show the user's hand: the composer, sent instructions, user rows in the event log, the "Ignored by you" pill, the node mark.

## The life of any command

1. **Click or key.** The control switches to its `is-sent` wording ("Pausing…", "Ignoring…"). Nothing else changes.
2. **Recorded.** The backend acknowledges the command. Still nothing else changes.
3. **Takes effect.** The effect arrives as events on the stream. Only now do pills, nodes, the queue and the log change. The log shows a `You` row with its sequence number.

Never skip to step 3 on the client. If the stream is disconnected, commands still send; the header says "reconnecting" and the controls stay in `is-sent`.

Commands that affect running nodes take effect at the node's next step boundary, not mid-step. The interface says so wherever it matters: "Takes effect at each node's next step", "applies when D2b finishes READING".

## Investigation level

| Action | State it applies in | What the user sees |
|---|---|---|
| Instruct the plan | Plan review | the graph is redrawn as a new plan version; the instruction and its diff appear in the right pane |
| Approve plan and start | Plan review | pill becomes Running; premise checks appear in Now |
| Pause | Running | "Pausing…", then pill "Paused · by you"; pulsing stops; Now empties as steps finish |
| Resume | Paused, Stopped | pill becomes Running; Next drains into Now |
| Finish now | Running, Paused | pill becomes Synthesising; the report will state it was ended early |
| Stop | Running, Paused | pill becomes Stopped; everything is kept; Resume and Finish into a report are offered |
| Raise limit and resume | Paused · spending limit | SystemPause banner with the new limit field |

## Node level

| Action | Key | Effect in the interface |
|---|---|---|
| Add instruction | I | focuses the composer, aimed at the selected node |
| Go deeper | D | the branch's Spend and Nodes meters in the inspector show a higher limit; a `You` row in the log |
| Run only this branch | F | header reads "Running only D2 · Run everything"; other nodes move to Next with "waits: you are running only D2" and dim |
| Pause / resume branch | Space | nodes in the branch become Paused (`warn`) and move to Not running |
| Ignore / restore branch | X | nodes become `ng-node--excluded`, edges `ng-edge--off`, pill "Ignored by you"; listed under Not running with a Restore link; restore brings back results already produced |
| Re-run node | R | inline `danger` confirmation in the inspector, then the node returns to Pending |

Ignore, restore, pause, go deeper and run-only apply immediately. They are reversible, so there is no confirmation.

## Instructing a node

1. **Select** the node in the graph, the queue or the log. The composer head shows the target and reach: "Instruct D2 · What astronauts report · reaches 4 nodes".
2. **Write** in plain language. Drafts are kept per node.
3. **Send** with the button or `⌘↵`. The instruction appears above the composer as queued, dashed, with what it is waiting for.
4. **Applied.** At the next step boundary the instruction block fills with `steer-wash` and shows its sequence number. The node gets a mark "✎ 1".
5. **Re-plan, if the node has children.** The coordinator compares its children with the instruction. The block gains a diff:
   - `= kept` children that still fit, with the results they already have;
   - `↺ superseded` children that no longer fit: stopped, hatched, restorable;
   - `+ proposed` new children, which appear dashed in the graph until the orchestrator approves them.
6. **Inherited.** Every descendant lists the instruction as inherited, dashed, with "from D2". Only the node it was given to carries the mark.

There is no confirmation before a re-plan. The diff is the receipt and each superseded child has a Restore button.

## What an instruction cannot do

- It cannot set a conclusion. If the text reads like one, the composer foot turns `warn`: "You can change what is investigated, not what is concluded. Netgrip will check this as a hypothesis." The user may still send it.
- It cannot remove a premise check. The diff answers: "P1 kept: premises are always checked".
- It cannot be edited or deleted after sending. Add another instruction; the node lists them in order.
- It cannot target the root once research has started. The root's composer is locked and says what to do instead. During plan review the root is the normal target.

## Where steering is recorded

- **Event log:** a `You` row on `steer-wash` for every intervention.
- **Graph:** marks on instructed nodes; hatching on excluded branches.
- **Inspector → Instructions:** inherited instructions from the root down, then the node's own.
- **Trail:** a `steer` rule at the step boundary where an instruction was applied.
- **Report → Limits of this investigation:** every exclusion and narrowing, as Instruction blocks.

## When Netgrip stops by itself

Netgrip pauses an investigation when the spending limit is reached, when the model or search service stays unavailable, or when a key is rejected. It never fails the investigation for these. The SystemPause banner states the cause, what was done, and the choices. A single page that cannot be fetched never pauses anything: the node shows "Retrying 2 of 3", then records the page as unobtainable and continues.

After a shutdown, running investigations continue without being asked. A neutral banner says so once: "Picked up where it stopped."
