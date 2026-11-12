# Field

Form controls for the new-investigation form and Settings: `ng-field` wraps a `ng-field__label`, one control and a `ng-field__hint`. Controls: `ng-input` (add `ng-input--mono` for money, domains, model ids), `ng-textarea`, `ng-select`, `ng-seg` (segmented choice), `ng-toggle`, `ng-keyfield` (write-only secret).

You provide the label, the value and a hint that states the consequence of the setting.

- Inputs sit in `sunken` with a `line-strong` border. Errors switch the border and hint to `danger` and say how to fix the value.
- `ng-seg` is for Effort and model presets only: three options, mutually exclusive, with the resulting budget shown beside it in `ng-mono`.
- `ng-keyfield` never renders a key. It shows "Key set" or "No key" and a Replace button. Replace swaps the row for an empty `ng-input--mono` that is cleared on save.
- Settings save on change. There is no Save button; show "Saved" in the hint for two seconds.
