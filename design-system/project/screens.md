# Screens and states

Seven screens, one per stage of an investigation. Each has a preview in the Screens group and a README with its regions and rules.

| Investigation state | Screen | The user's main action |
|---|---|---|
| (none) | ScreenInvestigations | New investigation |
| Draft | ScreenNewInvestigation | Draft the plan |
| Planning | ScreenPlanReview | Approve plan and start |
| Running, Paused, Stopped | ScreenControlBoard, with ScreenNodeDetail in its right pane | Send instruction; Resume when paused |
| Synthesising | ScreenControlBoard, read-only, then ScreenReport with headings only | none |
| Completed | ScreenReport; the board stays available as history | Ask a follow-up |
| any | ScreenSettings | none; changes save as made |

## The control board in one paragraph

A 60px header holds state, budget and run controls. Below it, three panes show the same nodes three ways. Left (284px), ExecutionOrder: Now, Next, Done, Not running. Centre, GraphCanvas with the EventLog docked under it. Right (364px), the inspector for the selected node, with Overview, Claims, Brief, Trail and Instructions tabs and the InstructionComposer pinned at the bottom. Selection is shared by all three.

## Which pane answers which question

| Question | Look at |
|---|---|
| What is running right now? | ExecutionOrder → Now; `live` nodes in the graph |
| What happens next, and why has it not started? | ExecutionOrder → Next |
| What already finished, and what did it find? | ExecutionOrder → Done; verdict line on each node |
| Why does this node exist? | inspector header "Why"; Brief → Path |
| What has it found so far? | inspector → Overview and Claims |
| What exactly did it do? | inspector → Trail |
| What did I tell it? | inspector → Instructions; `You` rows in the log |
| What did the orchestrator decide? | EventLog → Orchestrator filter |
| How much has this cost? | header meters; inspector meters for the branch |
| What did I exclude? | ExecutionOrder → Not running; hatched nodes |

## State vocabulary

Use StatusPill for lifecycle, ClaimStatus for evidence. The mapping from state to glyph, word and tone is fixed in those components and is the same on every screen.

## Empty, loading and error states

- **No investigations:** the prompt box takes the table's place.
- **Opening a board:** the snapshot arrives whole. Show the header and empty panes with "Loading the investigation" as an ActivityLine; no skeleton shimmer.
- **Stream disconnected:** header pill gains "· reconnecting" in `warn`; pulsing stops; on reconnect the log fills the gap and may insert "42 events while this tab was closed".
- **Nothing selected:** the inspector shows the root.
- **Nothing queued:** Next reads "Nothing queued. The orchestrator is deciding."
- **Paused:** Now reads "Nothing runs while paused".
- **No claims yet:** "No claims yet. They appear here as pages are read."
- **No model key:** "Draft the plan" is disabled with "Add a model key in Settings → Keys".
