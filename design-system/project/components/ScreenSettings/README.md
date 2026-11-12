# ScreenSettings

Defaults for every new investigation and the machine-wide limits, on one scrolling page with a section list at the left. Changes save as they are made.

| Section | Holds |
|---|---|
| Keys | model endpoint and key; search key. Write-only `ng-keyfield` rows with a status pill and the last check |
| Models | default preset; per-model table with tier, input and output price, and where the price came from |
| Effort | the budget behind Low, Medium, High: depth, nodes, sources per node, parallelism, sources needed to confirm |
| Spending | default spending limit; how long to retry a failing service before pausing |
| Sources | domains always excluded; page reuse window, including "Always fetch again"; per-site politeness |
| Capacity | investigations in parallel; model calls at once; browser pages at once, with live pool health |
| Storage | total disk use and data location; Rebuild state from history |

**Rules**

- A key is never displayed, not even masked characters. The row shows "Key set", "No key" or "Key rejected" with the provider's own message, and one button: Replace.
- A rejected key is `danger` here and raises the SystemPause banner on every investigation it paused.
- A model without a price gets empty `is-error` price inputs and a `warn` note. Until filled, any investigation using it shows "≈" before its spend.
- Effort values are editable numbers, labelled as starting values.
- Capacity shows what is in use now beside each limit, in `mono`.
- There is no account, profile, theme or notification section. The theme follows the system.
- Settings never appear in an exported report.
