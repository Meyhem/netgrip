# Field

Form controls for the new-investigation form and Settings: `ng-field` wraps a `ng-field__label`, one control and a `ng-field__hint`. Controls: `ng-input` (add `ng-input--mono` for money, domains, model ids), `ng-textarea`, `ng-select`, `ng-seg` (segmented choice), `ng-toggle`, `ng-keyfield` (write-only secret), `ng-combo` (searchable picker).

You provide the label, the value and a hint that states the consequence of the setting.

- Inputs sit in `sunken` with a `line-strong` border. Errors switch the border and hint to `danger` and say how to fix the value.
- `ng-seg` is for Effort and model presets only: three options, mutually exclusive, with the resulting budget shown beside it in `ng-mono`.
- `ng-keyfield` never renders a key. It shows "Key set" or "No key" and a Replace button. Replace swaps the row for an empty `ng-input--mono` that is cleared on save.
- Settings save on change. There is no Save button; show "Saved" in the hint for two seconds.
- `ng-combo` picks one value from a list too long for `ng-select`, such as a provider's models. An `ng-input--mono` with `role="combobox"` over an `ng-menu ng-combo__list`. Typing filters by fuzzy match: words in any order, letters in order with gaps; matched letters are `mark`ed. Each `ng-menu__item` holds the id in `b`, a right-aligned fact in `span` (price), and a `small` line (name, context). Arrow keys move `is-hover`, Enter picks, Escape restores the saved value. Picking saves at once, like any other setting.
