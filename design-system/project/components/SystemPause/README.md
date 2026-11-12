# SystemPause

A banner (`ng-banner`) for the moments Netgrip stops or restarts on its own and the user must know why. It sits between the board header and the three panes, full width.

You provide the pause reason and origin from the pause event, and the counts for the body line.

| Reason | Tone | Actions |
|---|---|---|
| Spending limit reached | warn | Raise limit and resume (with the new limit field), Finish now, Stop |
| Model or search service unavailable | warn | Resume, Show the errors in the log |
| Key rejected or credit exhausted | danger | Open Settings → Keys; Resume stays disabled until the key changes |
| Recovered after a shutdown | neutral | Dismiss (informational; the run continued by itself) |

- The title starts with "Paused:" and states the cause in plain words. The body says what is safe ("Nothing is lost") and what Netgrip did.
- The header pill repeats the origin: "Paused · spending limit".
- The banner stays until the user acts. It is not a toast and cannot be dismissed while the investigation is paused by the system.
- A user pause shows no banner. The pill "Paused · by you" is enough.
- A page that could not be fetched never raises a banner. That is a line in the node's trail and a count in the report.
