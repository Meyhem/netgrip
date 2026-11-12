# Button

Triggers a command. Class `ng-btn`, with one modifier: `ng-btn--steer` (the single primary action of a view), `ng-btn--quiet` (toolbar and dismissals), `ng-btn--danger` (the two irreversible actions: delete an investigation, re-run a node). Add `ng-btn--sm` inside panels, toolbars and node rows.

You provide the label and, optionally, a trailing `ng-kbd` shortcut hint.

- Label with the verb the event log will use: "Pause", "Ignore branch", "Approve plan". Never "OK" or "Submit".
- At most one `ng-btn--steer` per view. On the board it is the composer's "Send instruction"; in plan review it is "Approve plan".
- A command is acknowledged when recorded, not when it takes effect. After the click, set `is-sent` and the present participle ("Pausing…") until the matching event arrives. Never flip the status pill optimistically.
- `disabled` only for actions that cannot apply in the current state, and say why in a tooltip ("Nothing is paused").
