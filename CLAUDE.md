# Netgrip

Deep web research app: Python backend (uv), React frontend (Vite). Runs locally, single user.

## Where things are

- `docs/domain-spec.md` — domain concepts, rules and vocabulary. Use its terms exactly.
- `docs/tech-spec-netgrip.md` — architecture and decisions (D-xx), constraints (C-xx).
- `design-system/project/` — the design system: `README.md` (brand book), `steering.md`, `screens.md`, `tokens.json`, `components/bundle.css`, and a `README.md` + `preview.html` per component and screen. Published at https://claude.ai/artifact/Hquc2dsfMpk7DNrvkFJ8Rb.
- `docs/plans/` — implementation plans: `00-overview.md` (shared contracts: events, commands, routes, layout) and one file per phase, `01` to `08`. Do phases in order; each ends with a verification section.
- `design-system/build/` — scripts that generate the tokens and previews: `python3 tokens.py ../project && python3 screens.py ../project` (run from that folder; `screens.py` also builds the components).

Build UI from the design system: read `design-system/project/README.md` first, then the screen's own README.

## Git: push after every feature or fix

After each completed feature or fix, without being asked:

1. Run the relevant tests or checks. Do not commit work that is known to be broken.
2. `git add` the changed files and commit with a short imperative message describing the change.
3. `git push` to `origin` (`git@github.com:Meyhem/netgrip.git`), branch `main`.

One commit per feature or fix. Never commit secrets, API keys, the SQLite database or fetched page files. Never force-push or rewrite pushed history; if a push is rejected, stop and say so.
