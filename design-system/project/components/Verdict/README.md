# Verdict

A node's short conclusion and its confidence, shown at the top of the inspector as soon as it exists. A `ng-panel` with a "Verdict" label, an `ng-conf` readout, the verdict text in `body`, and one `mono` line of counts.

You provide the verdict text, confidence, claim and source counts, spend, and any relevance flag.

- Confidence is three bars and a word: Low, Medium, High. It is never a percentage.
- The counts line reports independent sources, spend and pages that could not be obtained.
- A verdict flagged off topic keeps its text in `ink-muted`, carries the dashed "OFF TOPIC" tag and says why it is kept out of the report.
- A failed node has no verdict. Say what was tried and offer the three ways out: Re-run node, Add instruction, Ignore branch.
- The verdict is the agent's text, shown as written. The UI adds no praise, hedging or summary of its own.
