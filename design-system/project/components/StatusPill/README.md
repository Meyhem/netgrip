# StatusPill

Shows one lifecycle state as a glyph and a word. Class `ng-pill` plus a tone: `--live`, `--ok`, `--warn`, `--danger`, `--steer`, or none (idle); `--ghost` makes the border dashed, `--hollow` drops the wash.

You provide the state. The glyph, word and tone are fixed by the tables below and never vary by screen.

| Investigation | Glyph | Tone |
|---|---|---|
| Draft | ○ | idle |
| Plan review | ✎︎ | steer (it is waiting for the user) |
| Running | ● (pulses) | live |
| Paused | ‖ | warn, always with its origin: "by you", "spending limit", "model service unavailable", "search unavailable", "key rejected" |
| Synthesising | ◐ | live |
| Completed | ✓ | ok |
| Stopped | ■ | idle |

| Node execution | Glyph | Tone |
|---|---|---|
| Proposed | ◌ | idle, ghost |
| Rejected | ⊘ | danger, hollow |
| Pending | ○ | idle |
| Running | ● (pulses) | live |
| Waiting on children | ◔ | live, hollow |
| Paused | ‖ | warn |
| Completed | ✓ | ok |
| Failed | ✕ | danger |

Inclusion is a second, independent pill shown only when a node is not Included: "Ignored by you" (steer, hollow) or "Superseded by re-plan" (ghost).

- Always glyph plus word. Colour never carries a state alone.
- A paused investigation always says who paused it. A system pause repeats its reason in the SystemPause banner.
- Do not invent states or soften words ("In progress", "Done"). Use the domain vocabulary exactly.
