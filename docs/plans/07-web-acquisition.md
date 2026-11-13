# Phase 7: Real web acquisition — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fake search and fetcher with the real ones: Tavily, an escalating fetcher, a strictly managed browser pool and a content extractor. First live run.

**Architecture:** Everything sits behind the Phase 4 interfaces (`Search`, `Fetcher`, extractor), so the engine does not change. The browser pool is the single owner of browser processes (D-22); a fetch borrows an isolated session for one page and always gives it back or destroys it.

**Tech stack:** httpx, playwright (Chromium), trafilatura, `pytest-httpserver` for local test pages.

**Spec:** domain spec 4.6 (W1–W5), V5, V8, V9; tech spec section 4 "Browser control", section 7, section 9, D-05, D-10, D-12, D-22, R-03, R-06, A-03, A-09.

## Global constraints

- Only the browser pool starts or stops browsers. A node never holds a browser across steps.
- Every browser operation has a deadline; nothing waits indefinitely.
- A session is closed on every exit path: success, error, timeout, cancellation. A session that cannot be closed takes its browser with it.
- Nothing is reused after a fault. Browsers are recycled after a fixed amount of use.
- A browser fault is a transient fetch failure: it never fails a node and never pauses an investigation.
- No proxies, no CAPTCHA solving (D-12). Own IP only; per-site politeness applies to every route.
- The fetcher only reads `http` and `https` URLs. Fetched content is data (P7).
- Tests that start a real browser are marked `@pytest.mark.browser` and use only local pages. Tests never call Tavily or the open web.
- Follow "Rules for every task" in the overview.

## Review focus

1. A page that keeps the connection open and never finishes loading: the fetch ends at its deadline and the session is gone (Task 3).
2. The Chromium process is killed from outside during five concurrent fetches: all five are retried on a fresh browser; none hangs (Task 3).
3. A URL pointing at `file:///etc/passwd`, `http://127.0.0.1:8321/api/settings` or a private address: refused without a request (Task 2).
4. A 30 MB PDF or binary download: abandoned at the size limit and recorded as unobtainable with the reason (Task 2).
5. Twenty URLs on one domain requested at once: sent no faster than the politeness setting (Task 2).

Deadlines and limits chosen here (A-09; all in settings under Capacity or as constants in `adapters/fetch_limits.py`): navigation 20 s; content wait 10 s; read 10 s; whole fetch 45 s; attempts per route 2 with delays 2 s then 6 s; maximum body 5 MB; browser recycled after 50 pages or 30 minutes.

---

### Task 1: Tavily search

**Files:** Create `adapters/search_tavily.py`, `tests/test_search_tavily.py`; wire in `engine/engine.py` when `config.fake` is false; add `POST /api/settings/keys/search/check`.

**Interfaces — produces:** `TavilySearch(get_key)` implementing `Search`; maps `exclude_domains` and `prefer == "primary"` (adds the instruction for official and original sources to the query options); 401/403 → `SearchRejected("key")`; 429 with a quota message → `SearchRejected("credit")`; other 429, 5xx, timeouts → `SearchUnavailable`.

- [ ] Tests (httpx `MockTransport`): `test_maps_results_to_hits`; `test_excluded_domains_sent_and_also_filtered_locally`; `test_invalid_key_rejected`; `test_quota_exhausted_rejected_credit`; `test_503_unavailable`; `test_key_not_in_logs_or_errors`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add Tavily search`.

### Task 2: Simple fetch, URL guard, politeness, extractor

**Files:** Create `adapters/{fetch_http.py,fetch_limits.py,url_guard.py,politeness.py,extractor.py}`, tests.

**Interfaces — produces:**
- `check_url(url) -> None | str` — a reason when the scheme is not http(s), or the host resolves to loopback, private, link-local or unspecified addresses.
- `Politeness(interval_s)`: `async wait(domain)` — at most one request per interval per registered domain, shared by all routes and investigations.
- `async fetch_simple(url, limits) -> FetchAttempt + PageContent | None` — httpx with a browser-like user agent; follows redirects (each hop passes `check_url`); stops at `max_body`; accepts `text/html`, `application/xhtml+xml`, `text/plain`; outcome `blocked` for 401, 403, 429 and for bodies that are challenge pages (short body with a known challenge marker); needs-JavaScript pages (text shorter than 200 characters after extraction) count as `error` so the fetch escalates.
- `extract(raw: bytes, url) -> Extracted(text, title, published_at)` — trafilatura to Markdown; returns the date only when the page states one (V5).

- [ ] Tests (`pytest-httpserver`): `test_fetch_simple_ok`; `test_redirect_to_private_address_refused`; `test_file_and_loopback_urls_refused_without_request`; `test_body_over_limit_abandoned`; `test_binary_content_type_unobtainable`; `test_403_is_blocked`; `test_empty_shell_page_escalates`; `test_politeness_spaces_requests` (fake clock: 20 requests to one domain take ≥ 38 s of fake time; another domain is not delayed); `test_extract_title_text_and_date`; `test_extract_no_date_when_absent`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add simple fetch, URL guard, politeness and extraction`.

### Task 3: Browser pool

**Files:** Create `adapters/browser_pool.py`, `tests/test_browser_pool.py` (marked `browser`).

**Interfaces — produces:**
- `BrowserPool(capacity: int, limits, profile_dir: Path, hardened: bool = False)`:
  - `async start()` — first removes leftovers from a previous run: every process recorded in `profile_dir/pids` that is still a Chromium started by us, and every temporary profile under `profile_dir`.
  - `async stop()` — closes every browser it started.
  - `session()` — `async with pool.session() as page:` gives a page in a fresh isolated context; at most `capacity` at once across all investigations. On exit the context is closed under a 5 s deadline; if closing fails or times out, the browser is killed and replaced. A session that raised or timed out is never reused.
  - `health() -> PoolHealth(open_pages, browsers, restarts_today, fetches_timed_out_today)`.
  - A watchdog detects a browser that has disconnected or does not answer a ping within 5 s, kills it, starts a new one, and fails the sessions that were on it with `BrowserFault` (retryable).
  - Recycling: a browser is closed and replaced after 50 pages or 30 minutes, once its sessions end.
- `async fetch_browser(pool, url, limits) -> FetchAttempt + PageContent | None` — navigation, content wait and read each under their deadline, the whole under the overall deadline; blocks image, media and font requests.
- Hardened mode (a second pool configuration, started on first need): launch argument `--disable-blink-features=AutomationControlled`, a current desktop user agent, locale and time zone of the machine, and an init script that removes `navigator.webdriver`.

- [ ] Tests against local pages served by `pytest-httpserver` (a normal page, one that never finishes, one that crashes the renderer via `chrome://crash` navigation, one that needs JavaScript to show its text): `test_fetches_js_rendered_text`; `test_hanging_page_times_out_and_session_is_closed` (no context left open: `len(browser.contexts) == 0`); `test_cancelled_fetch_leaves_no_page` (cancel the task mid-navigation); `test_crashed_page_discarded_and_pool_still_works`; `test_killed_browser_is_replaced_and_fetches_retry` (kill the process with `os.kill`; five concurrent fetches all end `ok` after retry); `test_capacity_never_exceeded` (capacity 2, six fetches, peak open pages 2); `test_browser_recycled_after_n_pages` (limit lowered to 3); `test_stop_closes_everything` (no child Chromium process remains); `test_startup_sweeps_leftovers` (start a pool, abandon it without `stop`, start a new pool on the same `profile_dir`: the old process is gone and old profiles removed).
- [ ] Fail, implement, pass. Run with `uv run pytest -m browser` (requires `uv run playwright install chromium`).
- [ ] Commit: `Add the browser pool with strict cleanup`.

### Task 4: Escalating fetcher

**Files:** Create `adapters/fetch_escalating.py`, `tests/test_fetch_escalating.py`; wire into `PageStore` in non-fake mode.

**Interfaces — produces:** `EscalatingFetcher(politeness, pool, hardened_pool, limits, clock)` implementing `Fetcher`. Order: simple, then browser, then hardened browser (W2). Within a route, a transient outcome (`timeout`, `error`, `BrowserFault`) is retried up to the attempt limit with increasing delay; `blocked` moves straight to the next route. `on_attempt(n, m, last)` is called before each retry so the node shows "Retrying n of m" (W1). When every route fails: `FetchResult(status="unobtainable", attempts=[…])` (W3). Cancellation propagates and leaves nothing open.

- [ ] Tests (routes replaced by scripted stubs; fake clock): `test_simple_success_uses_no_browser`; `test_escalates_simple_to_browser_to_hardened`; `test_blocked_skips_remaining_attempts_on_that_route`; `test_retry_delays_increase`; `test_on_attempt_reports_n_of_m`; `test_all_routes_fail_returns_unobtainable_with_every_attempt`; `test_browser_fault_counts_as_transient`; `test_cancel_during_browser_fetch_releases_session`.
- [ ] Fail, implement, pass.
- [ ] Commit: `Add the escalating fetcher`.

### Task 5: Source filters and capacity wiring

**Files:** Extend `engine/steps.py`, `engine/engine.py`, `api/system.py`, `store/settings.py`; tests.

**Behaviour:** excluded domains (settings default plus the investigation's own) are passed to search and enforced again before any fetch; an excluded URL is skipped and never recorded as unobtainable (W4). "Primary sources only" passes `prefer="primary"` and makes the node's decision prompt say so. Changing "Browser pages at once", "Model calls at once" or the politeness interval in Settings resizes the live pool and limiters without restart. `GET /api/system/pools` reports real browser use and `PoolHealth` ("now: 4 open · 2 restarts today · 7 fetches timed out"); pool events also go to the application log.

- [ ] Tests: `test_excluded_domain_never_fetched`; `test_excluded_domains_recorded_for_report_limits`; `test_capacity_change_resizes_pool`; `test_pools_endpoint_reports_health`.
- [ ] Fail, implement, pass. Frontend: Settings → Capacity and the top bar show the live figures (extend their tests with the health line).
- [ ] Commit: `Apply source filters and live capacity settings`.

### Task 6: Engine against the real fetcher, locally

**Files:** `tests/test_engine_local_web.py` (marked `browser`).

- [ ] One investigation with the fake model and fake search, but the real `EscalatingFetcher`, `BrowserPool` and extractor against a local site of ten pages (two hang, one needs JavaScript, one returns 403): it completes; the hanging pages are recorded unobtainable after visible retries; no node fails (E5); after `Engine.stop()` no Chromium process remains.
- [ ] Two investigations at once with pool capacity 2: peak open pages is 2; both complete (C-06).
- [ ] Kill simulation mid-fetch, then a new engine on the same data directory: leftovers swept, run completes, cached pages not refetched.
- [ ] Commit: `Test the engine against the real fetcher on local pages`.

---

## Phase verification

- [ ] `cd backend && uv run pytest && uv run pytest -m browser && uv run ruff check`; `cd frontend && npm test && npm run e2e` — all pass.
- [ ] After the browser tests: `pgrep -fa chromium` (or `chrome`) shows no process started from the test profile directory.
- [ ] **First live run** (manual; needs a model key and a Tavily key in Settings → Keys, both showing "Key set" after their check): start the backend without `NETGRIP_FAKE`, create a Low-effort investigation with a `$1.00` limit, approve the plan, and watch the board. Expected: real queries and URLs in activity lines; claims with sources; at least one retry or unobtainable page handled without a failed node; spend in the header close to the provider's dashboard (R-01); the run ends or pauses at the limit.
- [ ] During the live run: `kill -9` the backend, start it again. It continues by itself and no stray browser is left from before the kill.
- [ ] Run three Low-effort investigations at once and watch memory (R-03): open pages never exceed the setting; note the peak in the phase's commit message so A-03 can be revisited.

## Carried from Phase 4

- The page store does not remember an unobtainable URL per investigation (the node context reads past `page.unobtainable` events instead), so concurrent nodes can fetch a dead URL again with the full escalation: remember it in the store.
- The reconcile lock is held across model calls, so reconciling is serial per investigation, and the match prompt carries every known claim: revisit both with live latency and cost.
- `SearchRejected("request")` still pauses as `search_unavailable`, and each resume reruns the same refused query: treat it as a search with zero results (E5).
- Response schemas are strict-valid by our own check (`tests/test_schemas.py`), not yet against a live provider: confirm on the first live run.

## Carried from Phase 5

- `ng-src--lost` is dead against the backend: `sources.page_version_id` is NOT NULL and unobtainable pages are never linked to claims, yet the ClaimCard README lists LOST sources. Record unobtainable sources against the claims they were meant to support (a nullable `page_version_id` or a separate link), and test that the ClaimCard shows LOST. Phase 8 should check that the report handles them.
- Retries stream into the same trail step with no attempt marker, so the live text of a retried decision runs together: add a separator, or reset the text on retry, once real models stream.
- Re-check the per-delta render cost under real streaming rates (model text is folded in once per animation frame and only the trail's open step and the log's live rows re-render on it).
