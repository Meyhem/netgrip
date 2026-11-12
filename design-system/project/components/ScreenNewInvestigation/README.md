# ScreenNewInvestigation

The Draft state: the prompt, the settings for this run, and what it will roughly cost, before anything executes.

**Regions**

1. Left column, in this order: prompt (`ng-textarea` at 15/22), Effort (`ng-seg` with the resulting budget in `mono`), Models (preset `ng-seg` and a four-row tier table), source filters, page freshness, spending limit.
2. Right column, sticky: estimated cost as a range in `display`, per-tier split, "What happens next", and the steer button "Draft the plan".

**Rules**

- The prompt hint states the product's stance: the text is kept word for word and its assumptions are checked.
- Effort shows its consequences beside the control. The numbers come from Settings and are marked provisional there.
- The tier table says what each tier does and its rough share of cost. A model with no known price gets a `warn` hint, "No price on record. The spending limit will be approximate", with a link to Settings → Models.
- The Verifier row warns in `warn` when it shares a model family with Strong.
- The estimate is always a range and always says it is an estimate.
- The primary button is "Draft the plan", not "Start": research does not start here. It leads to ScreenPlanReview. If no model key is set, it is disabled and the hint reads "Add a model key in Settings → Keys".
- Every field here inherits its default from Settings and applies to this investigation only.
