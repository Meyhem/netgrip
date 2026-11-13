import pytest

from netgrip.adapters.extractor import extract
from netgrip.adapters.fetch_http import fetch_simple
from netgrip.adapters.fetch_limits import FetchLimits
from netgrip.adapters.politeness import Politeness
from netgrip.adapters.url_guard import check_url
from netgrip.engine.clock import FakeClock

PARAS = "".join(
    f"<p>Paragraph {i} about the Great Wall of China, its dynasties and its construction.</p>"
    for i in range(8)
)
PAGE = f"<html><head><title>The Wall</title></head><body><article>{PARAS}</article></body></html>"


def only(server):
    """A guard that lets the local test server through and applies the real guard elsewhere."""
    base = server.url_for("/")

    async def guard(url: str):
        return None if url.startswith(base) else check_url(url)

    return guard


async def test_fetch_simple_ok(httpserver):
    httpserver.expect_request("/p").respond_with_data(PAGE, content_type="text/html")
    attempt, page = await fetch_simple(httpserver.url_for("/p"), guard=only(httpserver))
    assert attempt.outcome == "ok" and attempt.route == "simple"
    assert "Great Wall" in page.text and page.title and page.raw == PAGE.encode()


async def test_redirect_to_private_address_refused(httpserver):
    httpserver.expect_request("/r").respond_with_data(
        "", status=302, headers={"Location": "http://169.254.169.254/latest/meta-data"}
    )
    attempt, page = await fetch_simple(httpserver.url_for("/r"), guard=only(httpserver))
    assert page is None and attempt.outcome == "error" and attempt.final
    assert "refused" in attempt.error


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1:8321/api/settings",
        "http://localhost:8321/api/settings",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://0.0.0.0/",
        "ftp://example.com/x",
        "http://169.254.169.254/",
    ],
)
async def test_file_and_loopback_urls_refused_without_request(httpserver, url):
    attempt, page = await fetch_simple(url)
    assert page is None and attempt.final and attempt.error.startswith("refused")
    assert httpserver.log == []


async def test_public_address_allowed():
    assert check_url("http://93.184.216.34/") is None


async def test_body_over_limit_abandoned(httpserver):
    httpserver.expect_request("/big").respond_with_data("x" * 3000, content_type="text/html")
    limits = FetchLimits(max_body=1000)
    attempt, page = await fetch_simple(httpserver.url_for("/big"), limits, guard=only(httpserver))
    assert page is None and attempt.final and "larger than" in attempt.error


async def test_binary_content_type_unobtainable(httpserver):
    httpserver.expect_request("/f.pdf").respond_with_data(
        b"%PDF-1.4 " + b"0" * 100, content_type="application/pdf"
    )
    attempt, page = await fetch_simple(httpserver.url_for("/f.pdf"), guard=only(httpserver))
    assert page is None and attempt.final and "application/pdf" in attempt.error


async def test_403_is_blocked(httpserver):
    httpserver.expect_request("/no").respond_with_data("denied", status=403)
    attempt, page = await fetch_simple(httpserver.url_for("/no"), guard=only(httpserver))
    assert attempt.outcome == "blocked" and page is None and not attempt.final


async def test_challenge_page_is_blocked(httpserver):
    html = "<html><head><title>Just a moment...</title></head><body>cf-challenge</body></html>"
    httpserver.expect_request("/c").respond_with_data(html, content_type="text/html")
    attempt, _ = await fetch_simple(httpserver.url_for("/c"), guard=only(httpserver))
    assert attempt.outcome == "blocked"


async def test_empty_shell_page_escalates(httpserver):
    shell = "<html><body><div id=app></div><script>render()</script></body></html>"
    httpserver.expect_request("/s").respond_with_data(shell, content_type="text/html")
    attempt, page = await fetch_simple(httpserver.url_for("/s"), guard=only(httpserver))
    assert attempt.outcome == "error" and not attempt.final and "JavaScript" in attempt.error
    assert page is None


async def test_404_is_final(httpserver):
    httpserver.expect_request("/missing").respond_with_data("gone", status=404)
    attempt, _ = await fetch_simple(httpserver.url_for("/missing"), guard=only(httpserver))
    assert attempt.final and "404" in attempt.error


async def test_politeness_spaces_requests():
    clock = FakeClock()
    p = Politeness(2.0, clock)
    start = clock.now()
    for _ in range(20):
        await p.wait("www.example.com")
    assert (clock.now() - start).total_seconds() >= 38
    mark = clock.now()
    await p.wait("other.org")
    assert clock.now() == mark  # another domain is not delayed
    await p.wait("blog.example.com")  # same registered domain: shares the schedule
    assert clock.now() > mark


async def test_politeness_concurrent_slots_are_evenly_spaced():
    clock = FakeClock()
    p = Politeness(2.0, clock)
    import asyncio

    start = clock.now()
    await asyncio.gather(*(p.wait("a.com") for _ in range(5)))
    assert len(clock.sleeps) == 4  # the fake clock advances on every sleep
    assert (clock.now() - start).total_seconds() >= 8


def test_extract_title_text_and_date():
    html = (
        "<html><head><title>The Wall</title>"
        "<meta property='article:published_time' content='2021-03-04'></head>"
        f"<body><article>{PARAS}</article></body></html>"
    ).encode()
    ex = extract(html, "https://x.org/a/2019/05/06/p")
    assert "Great Wall" in ex.text and ex.title and ex.published_at == "2021-03-04"


def test_extract_no_date_when_absent():
    ex = extract(PAGE.encode(), "https://x.org/a/2019/05/06/p")
    assert ex.published_at is None
