# EventLog

The investigation's recorded history, newest first, docked under the graph. One row per durable event: time, sequence number, who, what. Class `ng-log` with `ng-log__row` and an actor modifier.

You provide events from the snapshot and the live stream. The log renders them; it never summarises.

| Actor | Modifier | Who colour |
|---|---|---|
| You | `ng-log__row--you` | `steer`, on a `steer-wash` row: every intervention is findable at a glance |
| Orchestrator | `ng-log__row--orc` | `live` |
| A node (its id) | none | `ink` |
| Netgrip (the system) | `ng-log__row--sys` | `warn`: pauses, recovery, unobtainable pages |
| Streamed model text | `ng-log__row--eph` | italic `ink-faint`, sequence "live". Not stored; it disappears on reload |

- Sentence shape: verb first, then the object, then quoted text or numbers. "instructed D2", "approved D2c", "claim added", "completed".
- Filters are tags in the head: All, You, Orchestrator, Selected node, Claims, Problems. Counts appear when non-zero.
- "current to #0419" is the last sequence number applied. After a reconnect the log fills the gap silently; if the gap is long it inserts `ng-log__gap` ("42 events while this tab was closed").
- Follow keeps the newest row in view. Scrolling turns it off; the button turns it back on.
- Clicking a row selects its node. Clicking a sequence number in an Instruction or a report citation scrolls here.
- Keys, prompts to models and page bodies never appear in the log.
