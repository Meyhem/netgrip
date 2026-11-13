"""The browser pool: the one owner of browser processes (D-22).

Each browser is a Chromium we start ourselves, in its own process group and profile directory,
and drive over CDP. A fetch borrows an isolated context (`pool.session()`) and always gives it
back or destroys it. Pids and profiles are recorded on disk so the next run can sweep what a
crash left behind (tech spec section 4, "Browser control").
"""

import asyncio
import contextlib
import logging
import os
import shutil
import signal
import subprocess
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from playwright.async_api import Browser, Page, Playwright, async_playwright

from netgrip.adapters.fetch_limits import DEFAULT_LIMITS, USER_AGENT, FetchLimits
from netgrip.engine.limiter import Limiter

log = logging.getLogger(__name__)

PID_FILE = "pids"
PROFILE_PREFIX = "browser-"
LAUNCH_TIMEOUT_S = 20.0
BASE_ARGS = [
    "--headless=new",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--disable-background-networking",
    "--disable-extensions",
    "--disable-sync",
    "--mute-audio",
]
HARDENED_ARGS = ["--disable-blink-features=AutomationControlled"]
HARDENED_INIT_SCRIPT = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


class BrowserFault(Exception):
    """The browser died or stopped answering under a fetch. Retryable (transient)."""


@dataclass(frozen=True)
class PoolHealth:
    open_pages: int
    browsers: int
    restarts_today: int
    fetches_timed_out_today: int


def _machine_timezone() -> str:
    try:
        link = os.path.realpath("/etc/localtime")
        if "zoneinfo/" in link:
            return link.split("zoneinfo/", 1)[1]
    except OSError:
        pass
    return "UTC"


def _machine_locale() -> str:
    import locale

    code = locale.getlocale()[0] or ""
    return code.replace("_", "-") if code and code != "C" else "en-US"


class _Browser:
    def __init__(self, proc: asyncio.subprocess.Process, profile: Path, browser: Browser) -> None:
        self.proc = proc
        self.profile = profile
        self.browser = browser
        self.started = time.monotonic()
        self.pages = 0  # sessions started on it
        self.sessions = 0  # sessions open now
        self.retiring = False
        self.dead = False
        self.destroyed = False

    @property
    def usable(self) -> bool:
        return not self.dead and not self.retiring and self.proc.returncode is None


class BrowserPool:
    def __init__(
        self,
        capacity: int,
        limits: FetchLimits = DEFAULT_LIMITS,
        profile_dir: Path | None = None,
        hardened: bool = False,
        *,
        watchdog_interval_s: float = 2.0,
    ) -> None:
        self.limits = limits
        self.profile_dir = Path(profile_dir) if profile_dir else Path("browser-profiles")
        self.hardened = hardened
        self.watchdog_interval_s = watchdog_interval_s
        self._slots = Limiter("browser", capacity)
        self._pw: Playwright | None = None
        self._current: _Browser | None = None
        self._all: list[_Browser] = []
        self._lock = asyncio.Lock()
        self._watchdog: asyncio.Task | None = None
        self._started = False
        self._stopping = False
        self.open_pages = 0
        self.peak_open_pages = 0
        self.launches = 0
        self._day = datetime.now(UTC).date()
        self._restarts = 0
        self._timed_out = 0

    # --- bookkeeping -------------------------------------------------------------------

    def _today(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day, self._restarts, self._timed_out = today, 0, 0

    def health(self) -> PoolHealth:
        self._today()
        return PoolHealth(
            self.open_pages, len([b for b in self._all if not b.dead]),
            self._restarts, self._timed_out,
        )  # fmt: skip

    def note_timeout(self) -> None:
        self._today()
        self._timed_out += 1

    @property
    def capacity(self) -> int:
        return self._slots.capacity

    def resize(self, capacity: int) -> None:
        self._slots.resize(capacity)

    @property
    def pids(self) -> list[int]:
        return [b.proc.pid for b in self._all if not b.dead and b.proc.returncode is None]

    def context_counts(self) -> int:
        """Isolated contexts open now, across browsers (each browser has one default context)."""
        return sum(max(len(b.browser.contexts) - 1, 0) for b in self._all if not b.dead)

    # --- lifecycle ---------------------------------------------------------------------

    async def sweep(self) -> None:
        """Remove what a previous run left: our Chromium processes and temporary profiles."""
        await asyncio.to_thread(self._sweep_sync)

    def _sweep_sync(self) -> None:
        pid_file = self.profile_dir / PID_FILE
        if pid_file.exists():
            for line in pid_file.read_text().splitlines():
                pid_s, _, profile = line.partition("\t")
                if pid_s.isdigit() and profile and _is_ours(int(pid_s), profile):
                    log.info("sweeping leftover browser %s", pid_s)
                    _kill_group(int(pid_s))
            pid_file.unlink(missing_ok=True)
        if self.profile_dir.is_dir():
            for p in self.profile_dir.glob(f"{PROFILE_PREFIX}*"):
                shutil.rmtree(p, ignore_errors=True)

    async def start(self) -> None:
        if self._started:
            return
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        await self.sweep()
        self._pw = await async_playwright().start()
        self._started = True
        self._stopping = False
        self._watchdog = asyncio.create_task(self._watch(), name="browser-watchdog")

    async def stop(self) -> None:
        self._stopping = True
        if self._watchdog is not None:
            self._watchdog.cancel()
            await asyncio.gather(self._watchdog, return_exceptions=True)
            self._watchdog = None
        for b in list(self._all):
            await self._destroy(b)
        self._current = None
        if self._pw is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._pw.stop(), 5)
            self._pw = None
        self._started = False
        self._write_pids()

    # --- browsers ----------------------------------------------------------------------

    def _write_pids(self) -> None:
        lines = [f"{b.proc.pid}\t{b.profile}" for b in self._all if b.proc.returncode is None]
        pid_file = self.profile_dir / PID_FILE
        if lines:
            pid_file.write_text("\n".join(lines) + "\n")
        else:
            pid_file.unlink(missing_ok=True)

    async def _launch(self) -> _Browser:
        assert self._pw is not None
        profile = self.profile_dir / f"{PROFILE_PREFIX}{uuid.uuid4().hex[:12]}"
        profile.mkdir(parents=True)
        args = [
            self._pw.chromium.executable_path,
            *BASE_ARGS,
            *(HARDENED_ARGS if self.hardened else []),
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            "about:blank",
        ]
        proc = await asyncio.create_subprocess_exec(
            *args, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        # Recorded before anything can fail, so a crash right here is still swept next start.
        with contextlib.suppress(OSError):
            with (self.profile_dir / PID_FILE).open("a") as f:
                f.write(f"{proc.pid}\t{profile}\n")
        try:
            port = await asyncio.wait_for(self._debug_port(proc, profile), LAUNCH_TIMEOUT_S)
            pw_browser = await asyncio.wait_for(
                self._pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}"), LAUNCH_TIMEOUT_S
            )
        except BaseException:
            _kill_group(proc.pid)
            shutil.rmtree(profile, ignore_errors=True)
            raise
        b = _Browser(proc, profile, pw_browser)
        self._all.append(b)
        self.launches += 1
        pw_browser.on("disconnected", lambda _b=None, br=b: self._on_disconnect(br))
        log.info("browser started pid=%s hardened=%s", proc.pid, self.hardened)
        return b

    @staticmethod
    async def _debug_port(proc: asyncio.subprocess.Process, profile: Path) -> int:
        f = profile / "DevToolsActivePort"
        while True:
            if proc.returncode is not None:
                raise BrowserFault("the browser exited while starting")
            with contextlib.suppress(OSError, ValueError, IndexError):
                return int(f.read_text().split()[0])
            await asyncio.sleep(0.05)

    def _on_disconnect(self, b: _Browser) -> None:
        if not b.dead and not self._stopping:
            log.warning("browser pid=%s disconnected", b.proc.pid)
            b.dead = True
            self._restarts += 1
            self._schedule_cleanup(b)

    def _schedule_cleanup(self, b: _Browser) -> None:
        asyncio.get_running_loop().create_task(self._destroy(b, count=False))

    async def _destroy(self, b: _Browser, count: bool = False) -> None:
        """Kill the browser's whole process group, drop its profile. Safe to repeat."""
        b.dead = True
        if b.destroyed:
            return
        b.destroyed = True
        if count:
            self._restarts += 1
        if self._current is b:
            self._current = None
        await asyncio.to_thread(_kill_group, b.proc.pid)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(b.proc.wait(), 5)
        await asyncio.to_thread(shutil.rmtree, b.profile, True)
        if b in self._all:
            self._all.remove(b)
        with contextlib.suppress(OSError):
            self._write_pids()

    async def _acquire_browser(self) -> _Browser:
        async with self._lock:
            cur = self._current
            if cur is not None and cur.usable:
                age_min = (time.monotonic() - cur.started) / 60
                if cur.pages >= self.limits.recycle_pages or age_min >= self.limits.recycle_minutes:
                    cur.retiring = True
                    self._current = cur = None
                    self._retire_idle()
            else:
                cur = None
            if cur is None:
                cur = self._current = await self._launch()
            cur.pages += 1
            cur.sessions += 1
            return cur

    def _retire_idle(self) -> None:
        for b in list(self._all):
            if b.retiring and b.sessions == 0 and not b.dead:
                b.dead = True
                asyncio.get_running_loop().create_task(self._destroy(b))

    # --- sessions ----------------------------------------------------------------------

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[Page]:
        """A page in a fresh isolated context. Raises BrowserFault when the browser fails."""
        if not self._started:
            await self.start()
        async with self._slots:
            try:
                b = await self._acquire_browser()
            except BrowserFault:
                raise
            except Exception as e:
                raise BrowserFault(f"the browser could not start: {type(e).__name__}") from None
            ctx = None
            failed = False
            self.open_pages += 1
            self.peak_open_pages = max(self.peak_open_pages, self.open_pages)
            try:
                try:
                    ctx = await b.browser.new_context(**self._context_options())
                    if self.hardened:
                        await ctx.add_init_script(HARDENED_INIT_SCRIPT)
                    page = await ctx.new_page()
                except Exception as e:
                    failed = True
                    raise BrowserFault(f"the browser failed: {type(e).__name__}") from None
                try:
                    yield page
                except BaseException as e:
                    # Never reuse a session that raised or timed out; a dead browser is a fault.
                    failed = True
                    if not isinstance(e, asyncio.CancelledError | TimeoutError) and (
                        b.dead or b.proc.returncode is not None or not b.browser.is_connected()
                    ):
                        raise BrowserFault("the browser died during the fetch") from e
                    raise
            finally:
                self.open_pages -= 1
                await self._close_session(b, ctx, failed)

    def _context_options(self) -> dict:
        if not self.hardened:
            return {}
        return {
            "user_agent": USER_AGENT,
            "locale": _machine_locale(),
            "timezone_id": _machine_timezone(),
        }

    async def _close_session(self, b: _Browser, ctx, failed: bool) -> None:
        """Close the context under a deadline; if that fails the browser goes with it."""
        try:
            if ctx is not None and not b.dead:
                await asyncio.wait_for(asyncio.shield(ctx.close()), self.limits.close_s)
        except BaseException as e:  # includes a cancellation arriving during the close
            log.warning(
                "closing a browser context failed (%s): killing the browser", type(e).__name__
            )
            self._restarts += 1
            await asyncio.shield(self._destroy(b))
            b.sessions -= 1
            if isinstance(e, asyncio.CancelledError):
                raise
            return
        b.sessions -= 1
        if b.retiring:
            self._retire_idle()

    # --- watchdog ----------------------------------------------------------------------

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(self.watchdog_interval_s)
            for b in list(self._all):
                if b.dead:
                    continue
                if b.proc.returncode is not None or not await self._responds(b):
                    log.warning("browser pid=%s is gone or not answering: replacing", b.proc.pid)
                    await self._destroy(b, count=True)

    async def _responds(self, b: _Browser) -> bool:
        if not b.browser.is_connected():
            return False
        try:

            async def ping() -> None:
                s = await b.browser.new_browser_cdp_session()
                try:
                    await s.send("Browser.getVersion")
                finally:
                    await s.detach()

            await asyncio.wait_for(ping(), self.limits.ping_s)
            return True
        except Exception:
            return False


def _is_ours(pid: int, profile: str) -> bool:
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="ignore")
    except OSError:
        return False
    return f"--user-data-dir={profile}" in cmd


def _kill_group(pid: int) -> None:
    """SIGKILL the process group started for the browser (it leads its own session)."""
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.kill(pid, signal.SIGKILL)
