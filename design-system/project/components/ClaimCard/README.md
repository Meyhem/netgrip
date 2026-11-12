# ClaimCard

One atomic claim with its status and the sources for and against it. Class `ng-claim`; sources are `ng-src` rows (credibility tag, host and path, publication date).

You provide the claim text, status, id, producing node, and its supporting and contradicting sources with credibility and dates.

- Head: the ClaimStatus pill at left; the claim id and producing node at right in `mono`.
- Sources are grouped under "Supports · n independent" and "Contradicts · n". Contradicting URLs are `danger`. A page that could not be obtained is listed, struck through, tagged LOST.
- Dates are publication dates in ISO form. For time-sensitive questions, a stale source gets "retrieved 2026-11-12 · published 2019" in `warn`.
- A contradiction with a claim in another branch is named with that claim's id and node. Contradictions are shown, never resolved by the UI.
- "Verify this claim" proposes a Verification node. It is the only action on a claim.
- Clicking a source opens the stored page version used by this investigation, not the live web page.
