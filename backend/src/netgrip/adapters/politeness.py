"""Per-site politeness (D-12): at most one request per interval per registered domain, shared by
every route and every investigation."""

from netgrip.engine.clock import Clock, SystemClock

_SECOND_LEVEL = {"co", "com", "org", "net", "gov", "edu", "ac"}


def registered_domain(host: str) -> str:
    labels = host.lower().strip(".").split(".")
    if len(labels) <= 2 or all(p.isdigit() for p in labels):
        return ".".join(labels)
    if len(labels[-1]) == 2 and labels[-2] in _SECOND_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


class Politeness:
    def __init__(self, interval_s: float, clock: Clock | None = None) -> None:
        self.interval_s = interval_s
        self.clock = clock or SystemClock()
        self._next: dict[str, float] = {}

    def set_interval(self, interval_s: float) -> None:
        self.interval_s = interval_s

    async def wait(self, host: str) -> None:
        """Returns when a request to `host`'s site may be sent. Slots are reserved without
        awaiting, so concurrent callers get distinct, evenly spaced slots."""
        key = registered_domain(host)
        now = self.clock.now().timestamp()
        slot = max(now, self._next.get(key, now))
        self._next[key] = slot + self.interval_s
        if slot > now:
            await self.clock.sleep(slot - now)
