"""Claim status from the sources on each side (pure; domain spec evidence rules)."""

from dataclasses import dataclass
from typing import Literal

Credibility = Literal["Primary", "Reputable", "Weak"]
ClaimStatus = Literal["Confirmed", "Supported", "Unverified", "Contested", "Refuted"]

CREDIBLE: frozenset[str] = frozenset({"Primary", "Reputable"})


@dataclass(frozen=True)
class Source:
    id: str
    url: str
    title: str | None
    page_version_id: str
    credibility: Credibility
    published_at: str | None
    origin_key: str  # original publisher or wire report; the registered domain as fallback (V2)


def _credible_origins(sources: list[Source]) -> int:
    """Independent credible origins: articles sharing an origin_key count once (V2)."""
    return len({s.origin_key for s in sources if s.credibility in CREDIBLE})


def claim_status(
    supporting: list[Source], contradicting: list[Source], confirm_threshold: int
) -> ClaimStatus:
    pro, con = _credible_origins(supporting), _credible_origins(contradicting)
    if pro and con:
        return "Contested"
    if con >= confirm_threshold:
        return "Refuted"
    if pro >= confirm_threshold:
        return "Confirmed"
    if pro:
        return "Supported"
    return "Unverified"
