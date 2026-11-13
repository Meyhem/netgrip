# Netgrip

Deep web research on your own machine. Give it a question; it plans a graph of research steps, you review and approve the plan, then agents search and read the web, collect evidence, and synthesise a cited report. You can watch the run on a control board and steer it (focus, go deeper, ignore a branch, pause, finish now). Single user, runs locally, binds to loopback only.

## Stack

- Backend: Python 3.12, FastAPI, SQLite (event log plus state tables), managed with [uv](https://docs.astral.sh/uv/). Search through Tavily, fetching with plain HTTP escalating to a hardened Playwright browser, extraction with trafilatura.
- Model: any OpenAI-compatible endpoint; OpenRouter by default.
- Frontend: React, Vite, TypeScript, Zustand, built on the design system in `design-system/`.

## Run it

```bash
cd frontend && npm install && npm run build
cd ../backend && uv sync && uv run playwright install chromium
uv run netgrip
```

Open http://127.0.0.1:8321. The backend serves the built frontend. Set the model endpoint, model and API keys on the Settings screen.

Try it without keys or network using the scripted fake model and web:

```bash
NETGRIP_FAKE=1 uv run netgrip
```

| Variable | Default | Meaning |
|---|---|---|
| `NETGRIP_DATA_DIR` | `~/netgrip/data` | SQLite database and fetched pages |
| `NETGRIP_PORT` | `8321` | HTTP port |
| `NETGRIP_FAKE` | off | Use the fake model and web |
| `NETGRIP_FAKE_SCENARIO` | `great_wall` | Fake scenario (`great_wall`, `outage`) |
| `NETGRIP_FAKE_DELAY_MS` | `0` | Delay per fake model call |

For frontend development run `npm run dev` in `frontend/` (proxies `/api` to port 8321).

## Test

```bash
cd backend && uv run pytest        # browser tests excluded by default
cd frontend && npm test            # unit tests
cd frontend && npm run e2e         # Playwright end-to-end
```

Engine tests never touch the network.

## Layout

| Path | Contents |
|---|---|
| `backend/` | `netgrip` package: `engine/`, `adapters/`, `store/`, `api/`, `boundary/` |
| `frontend/` | The app, unit tests and `e2e/` |
| `contract/` | JSON contracts shared by backend and frontend tests |
| `design-system/` | Brand book, tokens, components, screen specs; `build/` regenerates them |
| `docs/` | `domain-spec.md`, `tech-spec-netgrip.md`, `plans/00-overview.md` (shared contracts), `backlog.md` |

Start with `docs/domain-spec.md` for the vocabulary and `docs/tech-spec-netgrip.md` for architecture. Contributor rules are in `CLAUDE.md`.
