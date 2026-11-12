Netgrip is a locally run deep web research tool. A user states a question or a claim; a graph of AI agents investigates it on the open web; the user watches the graph form, steers it, and gets an answer in which every statement traces to sources. This system covers the whole app: Investigations, New investigation, Plan review, the Control board, the Report and Settings.

## Four ideas the interface must make visible

1. **The research is visible.** Show the graph, each node's activity and each result the moment it exists. Never a spinner over a black box.
2. **The user steers it.** Everything the user did or is asked to do is `steer` pink. One glance at any screen should show where the user's hand has been.
3. **It verifies rather than agrees.** A refuted premise is `danger`, surfaced in the board header, in the list row, and first in the report.
4. **Nothing is lost.** Excluded work is greyed and hatched, never removed. Pauses say why and say "Nothing is lost".

## Colour

Two hues carry roles. Do not use them for anything else.

- `steer` (pink) is the user: instructions, interventions, the composer, user rows in the event log, node marks, and the single primary button of a view. Text on a `steer` fill is `on-steer`, never white by hand.
- `live` (cyan) is agents at work: Running and Waiting states, activity verbs, the edge path to running nodes. A finished graph has no `live` in it.

Three hues carry outcomes, always with a glyph and a word:

- `ok` (teal): Completed, Confirmed, Supported, a key that works.
- `warn` (amber): Paused, Retrying, Contested, budget above 80%.
- `danger` (orange-red): Failed, Refuted, Rejected, a rejected key, the two destructive actions.

Each has a `-wash` ground for pills and banners. `ok` leans blue so it never depends on red-green contrast with `danger`.

Neutrals: `bg` is the app ground and graph canvas; `surface` is panels and nodes; `raised` is menus and the selected row; `sunken` is inputs, the event log and wells. Text is `ink`, `ink-muted`, `ink-faint`, in that order of importance. `line` divides; `line-strong` outlines controls, nodes and edges.

Dark is the first theme: runs last for hours and are watched in the evening. Light is complete and equal. The theme follows the system; there is no toggle in the app.

Selection is a 2px `ink` outline. Focus is a solid 2px `focus` ring with 2px offset. Neither is ever pink.

## Type

Two families. `font-sans` (Instrument Sans) is the interface. `font-mono` (JetBrains Mono) is data: activity lines, the event log, URLs, queries, money, counts, ids, sequence numbers, kind codes.

- `display` for screen titles and the report's one-sentence answer. `title` for the investigation prompt in the board header and report sections. `heading` for panel heads and the node question in the inspector.
- `body` for verdicts, claims and instructions. `small` for node titles and hints.
- `label` is uppercase, tracked, always `ink-faint`: section and column heads only.
- `mono` and `mono-sm` use tabular figures. Money is always two decimals with a dollar sign: `$1.84 / $5.00`.

If something came from a machine or the web, set it in mono. If a person or an agent wrote it as a sentence, set it in sans.

## Space, shape, depth

- A 4px grid: `space-1` to `space-7`. Panels pad `space-3` or `space-4`. Rows gap `space-2`.
- `radius-md` on buttons, inputs, nodes, panels. `radius-lg` only on the composer and banners, the two things that address the user. `radius-pill` only on status pills and segmented controls. `radius-sm` on tags and key hints.
- Flat. Panels and nodes are separated by `line`, not shadow. `shadow-pop` is for menus only.
- Dashed borders mean "not real yet or not counted": Proposed, Planned, Rejected, Superseded, inherited or queued instructions, Weak sources.
- Hatching (`ng-node--excluded`) means excluded from the result.
- The graph ground is a 16px dot grid in `line`.

## Motion

One animation: the glyph of a running node pulses (`ng-pulse`, 1.4s). It stops when the investigation pauses, when the stream disconnects, and under `prefers-reduced-motion`. Nodes, panels and banners appear without transitions. State changes come from events, so nothing animates ahead of the truth.

## Iconography

There is no icon set. State glyphs are Unicode characters set in `font-mono`: ○ Pending, ◌ Proposed, ● Running, ◔ Waiting, ‖ Paused, ✓ Completed, ✕ Failed or Refuted, ⊘ Rejected, ⦸ Ignored, ↺ Superseded, ✎ instruction, ⇄ Contested, ✓✓ Confirmed, ? Unverified. Node kinds are mono codes: PRM, DIV, DEEP, VER, SYN. Actions are words, not icons. No emoji anywhere.

There is no logo. The wordmark is "netgrip" in `font-sans` 700, lowercase, with "grip" in `steer` (`ng-brand`).

## Voice

Plain, exact, unexcited. The interface reports; it does not reassure or sell.

- Use the domain's words exactly: investigation, node, branch, claim, source, verdict, premise, instruction, re-plan. States are Proposed, Pending, Running, Waiting on children, Paused, Completed, Failed; never "In progress" or "Done".
- Buttons are the verb the event log will record: "Pause", "Ignore branch", "Approve plan and start", "Finish now".
- Say the consequence and the scope: "Stops it and keeps its findings out of the report. You can restore it." "Reaches 4 nodes."
- Pauses and failures state the cause, what Netgrip did, and what is safe: "Paused: the model service stopped responding. Netgrip stopped retrying so it would not spend without progress."
- Address the user as "you". The system is "Netgrip", never "we" or "I".
- Be honest about uncertainty: "An estimate, not a quote." "Could not be verified." "Ended early by you."
- Tell the user when they are wrong, without softening: "Where you were wrong." "Your question assumed… The evidence refutes that."
- Sentence case everywhere. No exclamation marks. No "please", "sorry", "oops", "successfully".
- Numbers carry units and limits: `9 / 16 nodes`, `2 independent · 5 pages`, `Retrying 2 of 3`.

## How to build a screen

- Load `tokens.css`, then `components/bundle.css`. Put `class="ng"` on `body`. Components are plain CSS classes prefixed `ng-`; there is no JavaScript bundle.
- Start from the screen previews in the Screens group. Each screen's README lists its regions and rules.
- One `ng-btn--steer` per view. One selection shared by every pane.
- The frontend renders what the backend says. Controls show their `is-sent` wording until the confirming event arrives; never change a status pill optimistically.
- Confirm only what cannot be undone: deleting an investigation (the app's only modal) and re-running a node (inline). Everything else applies at once and can be reversed.
