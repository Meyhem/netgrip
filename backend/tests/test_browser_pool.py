import asyncio
import os
import signal
import subprocess

import pytest

from netgrip.adapters.browser_pool import BrowserFault, BrowserPool
from netgrip.adapters.fetch_browser import fetch_browser
from netgrip.adapters.fetch_limits import FetchLimits

pytestmark = pytest.mark.browser

PARAS = "".join(
    f"<p>Paragraph {i} about the Great Wall of China and its dynasties.</p>" for i in range(8)
)
NORMAL = f"<html><head><title>Wall</title></head><body><article>{PARAS}</article></body></html>"
JS_PAGE = (
    "<html><head><title>JS</title></head><body><div id=a></div><script>"
    "setTimeout(()=>{document.getElementById('a').innerHTML="
    f"'{PARAS}'"
    ";}, 300);</script></body></html>"
)
LIMITS = FetchLimits(navigation_s=3, content_wait_s=2, read_s=2, whole_s=6, close_s=3, ping_s=2)


async def allow(url: str):
    return None


def chromium_procs(profile_dir) -> list[str]:
    out = subprocess.run(["pgrep", "-fa", str(profile_dir)], capture_output=True, text=True)
    return [line for line in out.stdout.splitlines() if "pgrep" not in line]


@pytest.fixture
async def pool(tmp_path):
    p = BrowserPool(2, LIMITS, tmp_path / "profiles", watchdog_interval_s=0.3)
    await p.start()
    yield p
    await p.stop()


async def fetch(pool, url, limits=LIMITS):
    return await fetch_browser(pool, url, limits, guard=allow)


async def test_fetches_js_rendered_text(pool, httpserver):
    httpserver.expect_request("/js").respond_with_data(JS_PAGE, content_type="text/html")
    attempt, page = await fetch(pool, httpserver.url_for("/js"))
    assert attempt.outcome == "ok" and attempt.route == "browser"
    assert "Great Wall" in page.text


async def test_hanging_page_times_out_and_session_is_closed(pool):
    async def hang(reader, writer):
        await asyncio.sleep(60)

    server = await asyncio.start_server(hang, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    limits = FetchLimits(navigation_s=1, content_wait_s=1, read_s=1, whole_s=3, close_s=3)
    try:
        attempt, page = await fetch(pool, f"http://127.0.0.1:{port}/", limits)
    finally:
        server.close()
    assert attempt.outcome == "timeout" and page is None
    assert pool.context_counts() == 0 and pool.open_pages == 0
    assert pool.health().fetches_timed_out_today == 1


async def test_cancelled_fetch_leaves_no_page(pool):
    async def hang(reader, writer):
        await asyncio.sleep(60)

    server = await asyncio.start_server(hang, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    task = asyncio.create_task(fetch(pool, f"http://127.0.0.1:{port}/"))
    for _ in range(50):
        if pool.open_pages:
            break
        await asyncio.sleep(0.05)
    assert pool.open_pages == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    server.close()
    assert pool.open_pages == 0 and pool.context_counts() == 0


async def test_crashed_page_discarded_and_pool_still_works(pool, httpserver):
    httpserver.expect_request("/ok").respond_with_data(NORMAL, content_type="text/html")
    with pytest.raises(Exception):  # noqa: B017 - playwright reports the crash
        async with pool.session() as page:
            await page.goto("chrome://crash")
            await page.wait_for_timeout(500)
            await page.content()
    assert pool.context_counts() == 0
    attempt, _ = await fetch(pool, httpserver.url_for("/ok"))
    assert attempt.outcome == "ok"


async def test_killed_browser_is_replaced_and_fetches_retry(pool, httpserver):
    httpserver.expect_request("/ok").respond_with_data(NORMAL, content_type="text/html")

    async def slow(request):
        await asyncio.sleep(0)

    async def one(i):
        for _ in range(4):
            attempt, page = await fetch(pool, httpserver.url_for("/ok") + f"?{i}")
            if attempt.outcome == "ok":
                return attempt
            await asyncio.sleep(0.3)
        return attempt

    first = await fetch(pool, httpserver.url_for("/ok"))
    assert first[0].outcome == "ok"
    tasks = [asyncio.create_task(one(i)) for i in range(5)]
    await asyncio.sleep(0.05)
    for pid in pool.pids:
        os.killpg(pid, signal.SIGKILL)
    results = await asyncio.wait_for(asyncio.gather(*tasks), 60)
    assert [r.outcome for r in results] == ["ok"] * 5
    assert pool.health().restarts_today >= 1


async def test_capacity_never_exceeded(pool, httpserver):
    httpserver.expect_request("/ok").respond_with_data(NORMAL, content_type="text/html")
    results = await asyncio.gather(
        *(fetch(pool, httpserver.url_for("/ok") + f"?{i}") for i in range(6))
    )
    assert all(a.outcome == "ok" for a, _ in results)
    assert pool.peak_open_pages == 2


async def test_browser_recycled_after_n_pages(tmp_path, httpserver):
    httpserver.expect_request("/ok").respond_with_data(NORMAL, content_type="text/html")
    limits = FetchLimits(recycle_pages=3, whole_s=6, navigation_s=3, content_wait_s=2)
    p = BrowserPool(1, limits, tmp_path / "profiles")
    await p.start()
    try:
        for i in range(7):
            attempt, _ = await fetch(p, httpserver.url_for("/ok") + f"?{i}", limits)
            assert attempt.outcome == "ok"
        assert p.launches == 3
        await asyncio.sleep(0.3)
        assert len(p.pids) == 1  # the retired ones are gone
    finally:
        await p.stop()


async def test_stop_closes_everything(tmp_path, httpserver):
    httpserver.expect_request("/ok").respond_with_data(NORMAL, content_type="text/html")
    p = BrowserPool(2, LIMITS, tmp_path / "profiles")
    await p.start()
    await fetch(p, httpserver.url_for("/ok"))
    assert chromium_procs(tmp_path / "profiles")
    await p.stop()
    assert chromium_procs(tmp_path / "profiles") == []
    assert not list((tmp_path / "profiles").glob("browser-*"))


async def test_startup_sweeps_leftovers(tmp_path, httpserver):
    httpserver.expect_request("/ok").respond_with_data(NORMAL, content_type="text/html")
    profiles = tmp_path / "profiles"
    old = BrowserPool(1, LIMITS, profiles)
    await old.start()
    await fetch(old, httpserver.url_for("/ok"))
    old_pids = list(old.pids)
    assert old_pids and chromium_procs(profiles)
    # Abandon without stop: kill our own bookkeeping, leave the browser running.
    old._watchdog.cancel()
    new = BrowserPool(1, LIMITS, profiles)
    await new.start()
    try:
        for pid in old_pids:
            assert (
                not os.path.exists(f"/proc/{pid}")
                or open(f"/proc/{pid}/stat").read().split()[2] == "Z"
            )
        remaining = chromium_procs(profiles)
        assert remaining == []  # no browser until the new pool starts one
        assert len(list(profiles.glob("browser-*"))) == 0
    finally:
        await new.stop()
        await old._pw.stop()


async def test_hardened_hides_webdriver(tmp_path, httpserver):
    page_html = f"<html><head><title>w</title></head><body><p id=r></p><script>document.getElementById('r').textContent='webdriver='+navigator.webdriver;</script>{PARAS}</body></html>"
    httpserver.expect_request("/w").respond_with_data(page_html, content_type="text/html")
    p = BrowserPool(1, LIMITS, tmp_path / "h", hardened=True)
    try:
        attempt, page = await fetch(p, httpserver.url_for("/w"))
        assert attempt.route == "hardened" and "webdriver=undefined" in page.text
    finally:
        await p.stop()


async def test_session_after_stop_is_a_fault_not_a_hang(tmp_path):
    p = BrowserPool(1, LIMITS, tmp_path / "x")
    await p.start()
    await p.stop()
    p._started = True  # a stale pool must not hang a fetch
    with pytest.raises(BrowserFault):
        async with p.session():
            pass
