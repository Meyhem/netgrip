# BudgetMeter

A used-of-limit readout with a 4px bar: spend against the spending limit, nodes against the node limit, depth against the depth limit. Class `ng-meter`; add `ng-meter--warn` from 80% and `ng-meter--danger` at the limit.

You provide the label, the spent value and the limit.

- Money is always two decimals in `mono` with tabular figures. Limits are shown in `ink-faint` after a slash.
- The board header shows three meters: Spend, Nodes, Depth. The inspector shows the selected branch's own Spend and Nodes.
- If a model has no known price, append "≈" before the spend and link to Settings → Models. An estimate is never shown as exact.
- At the spending limit the meter turns `danger` and the SystemPause banner appears. The meter alone never explains a pause.
