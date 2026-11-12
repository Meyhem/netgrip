"""Plain text and title from fetched bytes (HTML or text). Stdlib only."""

from html.parser import HTMLParser

_SKIP = {"script", "style", "noscript", "template"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skip = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in {"p", "br", "div", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _SKIP and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def extract_text(raw: bytes, content_type: str = "text/html") -> tuple[str | None, str]:
    """Returns (title, text)."""
    html = raw.decode("utf-8", errors="replace")
    if "html" not in content_type:
        return None, html.strip()
    p = _Text()
    p.feed(html)
    lines = [" ".join(line.split()) for line in "".join(p.parts).splitlines()]
    return (p.title.strip() or None), "\n".join(line for line in lines if line)
