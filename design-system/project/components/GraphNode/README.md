# GraphNode

One node of the task graph: 172px wide, three lines. Line 1 is kind code, node id and state; line 2 the question (two lines at most); line 3 the activity while running, or the verdict summary once complete. Class `ng-node` plus `ng-node--proposed | rejected | pending | running | waiting | paused | done | failed | excluded`, and `is-selected`.

You provide the node's kind, id, question, execution status, inclusion and its latest activity or verdict.

| Kind | Code |
|---|---|
| Premise check | PRM |
| Divergent | DIV |
| Deep-dive | DEEP |
| Verification | VER |
| Synthesis | SYN |

- Running fills with `live-wash` and a `live` border; its glyph pulses. Waiting keeps the `live` border on a plain surface. Completed stays neutral with an `ok` state word, so a finished graph is calm and the live work stands out.
- Proposed is dashed and unfilled: it does not exist until the orchestrator approves it. Rejected is dashed, struck through, and keeps its reason in the inspector.
- Ignored and Superseded use `ng-node--excluded`: hatched and greyed, never hidden. Their edges use `ng-edge--off`.
- `ng-node__mark` ("✎︎ 1") in `steer` shows that the user has instructed this node, with the count. Descendants that only inherit the instruction show no mark; the inspector lists it as inherited.
- `ng-node__fold` collapses a branch ("−") or shows the hidden count ("+4").
- Selection is a 2px `ink` outline. It is never `steer` or `live`: selecting is not steering.
- The question is never rewritten or shortened by the UI beyond the two-line clamp. The full text and the justification are in the inspector.
