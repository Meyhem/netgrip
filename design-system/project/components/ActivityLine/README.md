# ActivityLine

One line saying what a running node is doing right now: an uppercase verb in `live` and the object in `ink-muted`, all in `mono`. Class `ng-activity` with `ng-activity__verb` and `ng-activity__what`.

You provide the activity and its detail from the latest activity event.

- Verbs are the eight domain activities only: Planning, Searching, Reading, Extracting, Reasoning, Aggregating, Waiting, Retrying n of m.
- The detail is always concrete: the query in quotes, the page as host and path, the count of claims. Never "Working…".
- Retrying uses `is-retry` (`warn`) and names the next fetch step: "full browser next", "hardened browser next", "last attempt".
- One line, truncated with an ellipsis at the end so the host stays visible. The full text is in the node's trail.
- Streamed model text is not an activity line. It appears only in the inspector's Trail tab while the node is open and is never stored.
