import asyncio

import pytest

from netgrip.adapters.browser_pool import BrowserFault
from netgrip.adapters.fetch_escalating import EscalatingFetcher
from netgrip.adapters.fetch_limits import FetchLimits
from netgrip.adapters.fetcher import FetchAttempt, PageContent
from netgrip.adapters.politeness import Politeness
from netgrip.engine.clock import FakeClock

URL = "https://example.com/a"


def ok(route):
    return FetchAttempt(route, "ok"), PageContent(URL, b"raw", "text " * 100)


def fail(route, outcome, **kw):
    return FetchAttempt(route, outcome, f"{outcome}", **kw), None


class Script:
    """A route stub that answers from a queue and counts its calls."""

    def __init__(self, route, *answers):
        self.route, self.answers, self.calls = route, list(answers), 0

    async def __call__(self, url):
        self.calls += 1
        a = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(a, Exception):
            raise a
        return a


def make(routes, clock=None, **limits):
    clock = clock or FakeClock()
    f = EscalatingFetcher(
        Politeness(0.0, clock), None, None, FetchLimits(**limits), clock, routes=routes
    )
    return f, clock


class Rec:
    def __init__(self):
        self.calls = []

    async def __call__(self, n, m, attempt):
        self.calls.append((n, m, attempt.outcome if attempt else None))


async def test_simple_success_uses_no_browser():
    browser = Script("browser", ok("browser"))
    f, _ = make({"simple": Script("simple", ok("simple")), "browser": browser})
    r = await f.fetch(URL, on_attempt=Rec())
    assert r.status == "ok" and [a.route for a in r.attempts] == ["simple"]
    assert browser.calls == 0


async def test_escalates_simple_to_browser_to_hardened():
    f, _ = make(
        {
            "simple": Script("simple", fail("simple", "error")),
            "browser": Script("browser", fail("browser", "timeout")),
            "hardened": Script("hardened", ok("hardened")),
        }
    )
    r = await f.fetch(URL, on_attempt=Rec())
    assert r.status == "ok"
    assert [(a.route, a.outcome) for a in r.attempts] == [
        ("simple", "error"), ("simple", "error"),
        ("browser", "timeout"), ("browser", "timeout"),
        ("hardened", "ok"),
    ]  # fmt: skip


async def test_blocked_skips_remaining_attempts_on_that_route():
    simple = Script("simple", fail("simple", "blocked"))
    f, _ = make({"simple": simple, "browser": Script("browser", ok("browser"))})
    r = await f.fetch(URL, on_attempt=Rec())
    assert simple.calls == 1 and r.status == "ok"


async def test_final_failure_stops_all_routes():
    browser = Script("browser", ok("browser"))
    f, _ = make(
        {"simple": Script("simple", fail("simple", "error", final=True)), "browser": browser}
    )
    r = await f.fetch(URL, on_attempt=Rec())
    assert r.status == "unobtainable" and browser.calls == 0 and len(r.attempts) == 1


async def test_retry_delays_increase():
    f, clock = make(
        {
            "simple": Script("simple", fail("simple", "error")),
            "browser": Script("browser", fail("browser", "error")),
            "hardened": Script("hardened", fail("hardened", "error")),
        }
    )
    await f.fetch(URL, on_attempt=Rec())
    assert clock.sleeps == [2.0, 6.0, 6.0]


async def test_on_attempt_reports_n_of_m():
    rec = Rec()
    f, _ = make(
        {
            "simple": Script("simple", fail("simple", "timeout"), ok("simple")),
        }
    )
    await f.fetch(URL, on_attempt=rec)
    assert rec.calls == [(1, 2, None), (1, 2, "timeout"), (2, 2, None), (2, 2, "ok")]


async def test_all_routes_fail_returns_unobtainable_with_every_attempt():
    f, _ = make(
        {
            "simple": Script("simple", fail("simple", "blocked")),
            "browser": Script("browser", fail("browser", "timeout")),
            "hardened": Script("hardened", fail("hardened", "error")),
        }
    )
    r = await f.fetch(URL, on_attempt=Rec())
    assert r.status == "unobtainable" and r.page is None
    assert [a.route for a in r.attempts] == ["simple", "browser", "browser", "hardened", "hardened"]


async def test_browser_fault_counts_as_transient():
    f, _ = make(
        {
            "simple": Script("simple", fail("simple", "blocked")),
            "browser": Script("browser", BrowserFault("died"), ok("browser")),
        }
    )
    r = await f.fetch(URL, on_attempt=Rec())
    assert r.status == "ok"
    assert r.attempts[1].outcome == "error" and "died" in r.attempts[1].error


async def test_cancel_during_browser_fetch_releases_session():
    open_sessions = []

    class FakePool:
        async def route(self, url):
            open_sessions.append(1)
            try:
                await asyncio.sleep(60)
            finally:
                open_sessions.pop()

    pool = FakePool()
    f, _ = make({"simple": Script("simple", fail("simple", "blocked")), "browser": pool.route})
    task = asyncio.create_task(f.fetch(URL, on_attempt=Rec()))
    for _ in range(20):
        await asyncio.sleep(0)
        if open_sessions:
            break
    assert open_sessions
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert open_sessions == []
