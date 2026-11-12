# ReportStatement

Report prose in which every statement carries its claims. Class `ng-report`; citations are `ng-cite` chips with the claim id; statements below Confirmed are wrapped in `ng-hedge`.

You provide the stored report structure: statements with the claim ids they rest on.

- Report text is `body` at 15/24 in a 680px column. Section titles use `title`.
- Every sentence that states a fact ends with at least one `ng-cite`. Clicking one opens the claim inline in an `ng-well` (status, independent sources, producing node, hosts) and selects the node on the board.
- A statement whose claim is Supported, Unverified or Contested gets the dashed `warn` underline (`ng-hedge`) and wording that says so: "may", "one source reports". It is never written as plain fact.
- "Where you were wrong" is a `danger` banner directly under the answer whenever a premise was refuted. It quotes the assumption and cites the premise node.
- Section order is fixed: The answer, Where you were wrong, Key findings, What could not be verified, Limits of this investigation.
