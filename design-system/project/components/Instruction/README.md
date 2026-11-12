# Instruction

A sent instruction, shown verbatim. Class `ng-instr` (given here, applied), `ng-instr--inherited` (dashed, from an ancestor), `ng-instr--queued` (dashed, waiting for a step boundary).

You provide the instruction text, when it was sent, the node it was given to and its application event.

- The text is the user's own words, unedited, in `ink` on `steer-wash`. Meta is `steer` in `mono-sm`.
- Order in the inspector: inherited instructions first, from the root down, then the node's own, oldest first. This is the order the agent reads them in its brief.
- Every instruction links to its event in the log by sequence number.
- The same block appears in the report's "Limits of this investigation" for any instruction that narrowed the research.
