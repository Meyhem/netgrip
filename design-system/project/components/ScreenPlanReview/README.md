# ScreenPlanReview

The Planning state. The user sees the first decomposition as a graph, reshapes it with instructions, and approves it. No web research runs on this screen.

**Regions**

1. Board header: the "Plan review" pill in `steer`, the prompt as `title`, Spend (planning already costs model calls) and Planned nodes, then "Discard draft" and the steer button "Approve plan and start".
2. Centre: toolbar with the plan version and what the last instruction changed; the GraphCanvas with every node dashed ("Planned"); the InstructionComposer docked underneath, aimed at the root.
3. Right pane: root goal; the assumptions extracted from the prompt, each a Premise check; the user's instructions so far, newest first, each with its diff; a short "On approval" note on execution order.

**Rules**

- Every node is `ng-node--proposed` with the state word "Planned". Nothing is live, so nothing is `live` coloured.
- Each instruction redraws the graph. Nodes it added carry a `steer` mark "new" until the next instruction; nodes it removed stay for that one version as `ng-node--excluded` with "− Removed", then leave the canvas. They remain in the instruction's diff.
- "Undo last instruction" returns to the previous plan version. Versions are numbered in the toolbar.
- The composer's own button is the neutral "Re-plan"; the single steer button on this screen is "Approve plan and start".
- The assumptions block uses the user's wording and explains the stance in one sentence. It is not optional and cannot be removed by instruction; an instruction that tries is answered in the diff: "P1 kept: premises are always checked".
- While a re-plan is being computed, the toolbar shows "Re-planning…" as an ActivityLine and Approve is disabled.
- Leaving the screen keeps the plan. The list shows the row as "Plan review" under Needs you.
