# GraphCanvas

The live task graph: nodes laid out left to right by depth on a dotted 16px ground, joined by two kinds of edge. Class `ng-canvas` holding one `svg` of `ng-edge` paths and absolutely placed `ng-node` elements.

You provide node positions from the layout and the edge list. The canvas computes no research state.

- Depth runs left to right, so the root goal is always at the left edge and reading order matches the path in a node's brief.
- Decomposition is a solid `line-strong` curve from parent to child. Dependency is a dashed `ink-muted` line with an arrowhead pointing at the node that waits.
- The chain of edges from the root to each running node is `ng-edge--live`. This is the "highlight active work" aid and is on by default.
- Edges into Ignored or Superseded nodes are `ng-edge--off`.
- New nodes appear in place as Proposed (dashed) and become solid on approval. Nothing animates beyond the running glyph's pulse; with `prefers-reduced-motion` that stops too.
- Toolbar actions above the canvas: Fit, Collapse completed, Show excluded (on by default), Follow active. Collapsed branches show `ng-node__fold` with the hidden count.
- Click selects a node and opens it in the inspector. Double-click folds its branch. Right-click or `.` opens NodeActions.
