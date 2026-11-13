"""A local site for tests of the real fetcher: normal pages, hanging ones, a JavaScript one and
a 403, served by a tiny asyncio HTTP server (no network beyond 127.0.0.1)."""

import asyncio
import json
import subprocess
from collections import Counter
from pathlib import Path

from netgrip.adapters.fakes import FakeSearch
from netgrip.adapters.fetch_limits import FetchLimits
from netgrip.adapters.web import Web
from netgrip.engine.clock import FakeClock

SCENARIO = Path(__file__).parents[1] / "src/netgrip/adapters/fake_scenarios/great_wall_web"
FILLER = (
    "This page is part of a local test site and carries enough running text for the "
    "extractor to keep it as the main content of the page."
)
LIMITS = FetchLimits(
    navigation_s=1.5,
    content_wait_s=1,
    read_s=1,
    whole_s=4,
    close_s=3,
    ping_s=2,
    retry_delays_s=(0, 0),
)


def html(title: str, text: str, script: str = "") -> bytes:
    body = f"<article><h1>{title}</h1><p>{text}</p><p>{FILLER} Page: {title}.</p></article>"
    return f"<html><head><title>{title}</title></head><body>{body}{script}</body></html>".encode()


class LocalSite:
    def __init__(self) -> None:
        pages = json.loads((SCENARIO / "pages.json").read_text())
        by_name = {"/nasa": "nasa/great-wall-from-orbit", "/myth": "history/wall-myth",
                   "/enc": "encyclopedia/great-wall"}  # fmt: skip
        self.pages: dict[str, bytes] = {}
        for path, key in by_name.items():
            spec = pages[f"https://example.org/{key}"]
            self.pages[path] = html(spec["title"], spec["text"])
        js_text = "Rendered by script: the wall is hard to see from orbit."
        self.pages["/js"] = (
            "<html><head><title>JS</title></head><body><div id=a></div><script>"
            "setTimeout(()=>{document.getElementById('a').innerHTML="
            f"'<article><h1>JS</h1><p>{js_text}</p><p>{FILLER} Page: JS.</p>"
            "<p>A second paragraph that the script adds, with different words in it.</p></article>'"
            "},300);</script></body></html>"
        ).encode()
        self.hangs = {"/hang1", "/hang2"}
        self.hits: Counter[str] = Counter()
        self.server: asyncio.AbstractServer | None = None
        self.port = 0

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    async def start(self) -> "LocalSite":
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def stop(self) -> None:
        self.server.close()

    async def _handle(self, reader, writer) -> None:
        try:
            line = await reader.readline()
            while (await reader.readline()).strip():
                pass
            if len(parts := line.decode().split(" ")) < 2:
                return  # a speculative connection that sent nothing
            path = parts[1].split("?")[0]
            self.hits[path] += 1
            if path in self.hangs:
                await asyncio.sleep(60)
            if path == "/forbidden":
                status, body = "403 Forbidden", b"denied"
            elif path in self.pages:
                status, body = "200 OK", self.pages[path]
            else:
                status, body = "404 Not Found", b"gone"
            head = (
                f"HTTP/1.1 {status}\r\nContent-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
            )
            writer.write(head.encode() + body)
            await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            writer.close()

    def search(self) -> FakeSearch:
        def hit(path, title):
            return {"url": self.url(path), "title": title, "snippet": title, "published_at": None}

        return FakeSearch({
            "results": [{"match": "visible", "hits": [
                hit("/nasa", "NASA"), hit("/forbidden", "Forbidden"), hit("/hang1", "Hangs"),
                hit("/js", "JavaScript page"), hit("/myth", "Myth"),
            ]}],
            "default": [hit("/enc", "Encyclopedia"), hit("/hang2", "Hangs too")],
        })  # fmt: skip


async def no_guard(url: str):
    return None


def make_web(path: Path, site: LocalSite, pages: int = 2) -> Web:
    async def no_key():
        return None

    return Web(
        path / "browser", no_key, pages, 0.0, LIMITS,
        guard=no_guard, clock=FakeClock(), search=site.search(),
    )  # fmt: skip


def browsers_running(path: Path) -> list[str]:
    out = subprocess.run(["pgrep", "-fa", str(path)], capture_output=True, text=True)
    return [x for x in out.stdout.splitlines() if "pgrep" not in x and "--user-data-dir" in x]
