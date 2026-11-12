# Brief

What a node was given: root goal, path, justification, own task, scope fence, definition of done, what is already known, and budget. A definition list, `ng-brief`.

You provide the node's stored brief. Show it as the agent received it.

- Rows, in this order: Root goal, Path, Why, Task, Out of scope, Done when, Known, Budget. Instructions are shown separately, as Instruction blocks, directly under the brief.
- Root goal is the user's prompt, verbatim, on every node at every depth.
- Path lists one line per ancestor; ancestors in `ink-muted`, the node itself in `ink`.
- "Why" is the node's justification. It is the first thing to read when judging whether a node has drifted, so it also appears under the question at the top of the inspector.
- Known lists claim ids and dependency results, not their text. Each is a link.
- The brief is read-only. To change a node's direction, add an instruction.
