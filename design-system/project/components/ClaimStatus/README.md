# ClaimStatus

The evidence vocabulary: five claim statuses, three premise outcomes and three source credibility classes. Statuses are `ng-pill`; credibility is `ng-tag` (`--solid` Primary, plain Reputable, `--dashed` Weak).

You provide the status computed by the evidence service. The UI never derives one.

| Status | Glyph | Tone | Meaning |
|---|---|---|---|
| Confirmed | ✓✓ | ok | enough independent sources for the chosen effort |
| Supported | ✓ | ok, hollow | supported, below the confirmation bar |
| Unverified | ? | idle | single or weak source only |
| Contested | ⇄ | warn | credible sources disagree |
| Refuted | ✕ | danger | credible evidence shows it is false |

- Source counts state independence, not pages: "2 independent · 5 pages". Independence is by origin.
- Credibility weight goes from filled to outline to dashed, so it reads without colour.
- A refuted premise is `danger` wherever it appears and is repeated at the top of the report under "Where you were wrong".
- Confidence on a verdict uses `ng-conf` (three bars and a word), not these pills.
