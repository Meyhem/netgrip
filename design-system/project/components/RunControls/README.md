# RunControls

The investigation-level commands, shown at the right of the board header. Which buttons appear is fixed by the investigation's state.

You provide the investigation state. Each button sends one command.

| State | Controls |
|---|---|
| Plan review | **Approve plan**, Discard draft |
| Running | Pause, Finish now, Stop |
| Paused | **Resume**, Finish now, Stop |
| Synthesising | none |
| Stopped | **Resume**, Finish into a report |
| Completed | Open report, Export Markdown |

- Pause: no new work starts; running steps finish. The button reads "Pausing…" until the paused event arrives.
- Finish now: stops exploring and writes the report from what exists. The report will say it was ended early. No confirmation.
- Stop: ends execution without a report and keeps everything. It is resumable, so there is no confirmation.
- None of these asks "Are you sure?". Each is reversible or resumable, and the event log records it.
- Resume is the steer button whenever the investigation is waiting for the user.
