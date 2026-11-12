# InstructionComposer

Where the user steers with words. A bordered `steer` box (`ng-composer`) with a head naming the target and reach, a textarea, and a foot that states when the instruction takes effect. It is the only place on the board that takes free text.

You provide the target node, the size of its branch, and whether the target has children (which decides the foot copy).

**Placement.** In plan review it is docked under the graph and aimed at the root. On the board it is pinned to the bottom of the inspector and aimed at the selected node. `I` focuses it; `⌘↵` sends; `Esc` returns focus to the graph and keeps the draft.

**The four states of an instruction**

1. Draft: text in the composer. Kept per node until sent or cleared.
2. Queued: the command is recorded. The instruction appears above the composer as `ng-instr--queued` with what it is waiting for ("applies when D2b finishes READING"). Instructions never interrupt a step.
3. Applied: `ng-instr` filled with `steer-wash`, stamped with the event sequence number. If the target is a coordinator, an `ng-diff` lists what the re-plan kept, superseded and proposed.
4. Inherited: on every descendant the same instruction appears as `ng-instr--inherited` with "from D2". It cannot be edited there.

**Rules**

- The head always states reach: "reaches 4 nodes". An instruction applies to the node and all its descendants.
- A re-plan applies at once, without a confirmation step. The diff is the receipt, and each superseded child has a Restore button.
- Instructions change scope and direction only. When the text reads like a conclusion, the foot turns `warn` and says so; the user may still send it, and it is treated as a hypothesis.
- Instructions are never deleted or edited after sending. A new instruction is added after the old one; the node's Instructions list shows them in order.
- The root is instructable only during plan review. After approval its composer is `is-locked` and explains what to do instead.
- Everything the user excluded this way is listed in the report under "Limits of this investigation".
