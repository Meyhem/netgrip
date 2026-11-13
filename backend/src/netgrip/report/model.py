"""The structured report (D-16): sections of statements, each carrying the claim ids it rests
on, plus the limits of the investigation. Rules R1 and R2 are checked here, in code, after the
model has written (`validate_report`); they are never left to the prompt."""

from collections.abc import Iterable
from typing import Literal

from pydantic import BaseModel, Field

from netgrip.evidence.service import Claim

SectionKey = Literal["answer", "wrong", "findings", "unverified", "limits"]

# Fixed order and titles (domain spec 4.11). "wrong" is present exactly when a premise was refuted.
TITLES: dict[str, str] = {
    "answer": "The answer",
    "wrong": "Where you were wrong",
    "findings": "Key findings",
    "unverified": "What could not be verified",
    "limits": "Limits of this investigation",
}
ORDER: list[str] = list(TITLES)
CONFIRMED = "Confirmed"


class Statement(BaseModel):
    text: str
    claim_ids: list[str] = Field(default_factory=list)
    hedged: bool = False
    premise_node_id: str | None = None  # in "wrong": the premise check that refuted it (P1)


class Section(BaseModel):
    key: SectionKey
    title: str
    statements: list[Statement] = Field(default_factory=list)


class ExcludedBranch(BaseModel):
    display_id: str
    question: str
    by: str  # user / replan


class LimitInstruction(BaseModel):
    text: str
    node_display_id: str | None = None
    seq: int


class Limits(BaseModel):
    effort: str
    confirm_threshold: int
    ended_early: bool = False
    cut_short_by: Literal["budget", "spending_limit", "finish_now"] | None = None
    unobtainable_pages: list[str] = Field(default_factory=list)
    excluded_branches: list[ExcludedBranch] = Field(default_factory=list)
    instructions: list[LimitInstruction] = Field(default_factory=list)
    excluded_domains: list[str] = Field(default_factory=list)


class Totals(BaseModel):
    claims: int = 0
    sources: int = 0
    nodes: int = 0
    spent_usd: float = 0.0


class Report(BaseModel):
    id: str
    investigation_id: str
    created_at: str
    answer_confidence: Literal["low", "medium", "high"]
    sections: list[Section]
    limits: Limits
    totals: Totals = Field(default_factory=Totals)

    def section(self, key: str) -> Section | None:
        return next((s for s in self.sections if s.key == key), None)


def validate_report(
    report: Report,
    claims: dict[str, Claim],
    *,
    refuted_premises: Iterable[str] = (),
    excluded_claim_ids: Iterable[str] = (),
) -> list[str]:
    """Errors for everything the report breaks; empty when it is valid.

    `claims`: the claims the report may cite by id. `excluded_claim_ids`: claims of nodes that
    are not Included or are off-topic (U4, E3): citing one is an error even if it is in `claims`.
    `refuted_premises`: ids of the premise-check nodes whose premise was refuted (P1)."""
    errors: list[str] = []
    refuted = list(refuted_premises)
    excluded = set(excluded_claim_ids)
    keys = [s.key for s in report.sections]
    expected = [k for k in ORDER if k != "wrong" or "wrong" in keys]
    if keys != expected:
        errors.append(f"sections must be {expected} in that order, got {keys}")
    for s in report.sections:
        if s.title != TITLES.get(s.key):
            errors.append(f"section {s.key!r} must be titled {TITLES.get(s.key)!r}")
    wrong = report.section("wrong")
    if wrong is not None and not refuted:
        errors.append("'Where you were wrong' is present but no premise was refuted")
    if refuted:
        covered = {st.premise_node_id for st in (wrong.statements if wrong else [])}
        for node_id in refuted:
            if node_id not in covered:
                errors.append(f"refuted premise {node_id} has no statement in 'wrong'")
    for s in report.sections:
        if s.key == "limits":
            continue
        for i, st in enumerate(s.statements, start=1):
            where = f"{s.key} statement {i}"
            if not st.claim_ids:
                errors.append(f"{where} cites no claim (R1): {st.text[:60]!r}")
                continue
            cited: list[Claim] = []
            for cid in st.claim_ids:
                if cid in excluded:
                    errors.append(f"{where} cites claim {cid} of an excluded or off-topic node")
                elif cid not in claims:
                    errors.append(f"{where} cites unknown claim {cid}")
                else:
                    cited.append(claims[cid])
            if cited and len(cited) == len(st.claim_ids):
                if all(c.status != CONFIRMED for c in cited) and not st.hedged:
                    errors.append(f"{where} rests on claims below Confirmed and is not hedged (R2)")
    return errors
