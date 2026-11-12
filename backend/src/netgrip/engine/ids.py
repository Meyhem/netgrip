"""Display ids: R, P1, D1, V1, S; deeper levels alternate a letter and a number."""

_PREFIX = {"Premise check": "P", "Divergent": "D", "Verification": "V"}


def next_display_id(kind: str, parent_display_id: str | None, taken: set[str]) -> str:
    if parent_display_id is None:
        return "S" if kind == "Synthesis" else "R"
    if parent_display_id == "R":
        stem, numeric = _PREFIX.get(kind, "D"), True
    elif parent_display_id[-1].isdigit():
        stem, numeric = parent_display_id, False
    else:
        stem, numeric = parent_display_id, True
    n = 1
    while True:
        suffix = str(n) if numeric else chr(ord("a") + (n - 1) % 26) * (1 + (n - 1) // 26)
        if stem + suffix not in taken:
            return stem + suffix
        n += 1
