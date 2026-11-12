# NodeActions

The node-level interventions, as a menu (`ng-menu`) opened from a node and as the action row at the top of the inspector. Every item is a verb, a one-line consequence and a shortcut.

You provide the selected node, its branch size and its state. The menu decides which items apply.

| Action | Key | Applies when | Effect |
|---|---|---|---|
| Add instruction | I | always, except the root once research has started | opens the InstructionComposer aimed at this node |
| Go deeper | D | node is Included | grants the branch more budget; the BudgetMeter in the inspector shows the new limit |
| Run only this branch | F | investigation is Running | everything outside the branch waits; the header shows "Running only D2 · Run everything" |
| Pause / Resume branch | Space | node is Pending, Running or Waiting / Paused | suspends or continues this branch only |
| Ignore / Restore branch | X | always | toggles inclusion for the whole branch |
| Re-run node | R | node is Completed or Failed | discards the result and runs it again |

- The consequence line always names the scope: "this node and its 4 descendants".
- Ignore, Restore, Pause, Go deeper and Run only this branch apply at once with no confirmation, because each can be undone.
- Re-run node is the one destructive node action. It asks once, inline in the inspector, with a `danger` banner. No modal.
- Items that do not apply stay visible, disabled, with the reason as their consequence line.
- After a command the item shows the `is-sent` wording ("Ignoring…") until the event arrives.
