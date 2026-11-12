"""Durable event envelope and the registry of versioned event data shapes (R-05).

A shape never changes in place: a new shape gets a new `v` and an upcaster from the old one.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Actor = Literal["user", "orchestrator", "node", "system"]
Origin = Literal["user", "system", "orchestrator"]
InvestigationState = Literal[
    "Draft", "Planning", "Running", "Paused", "Synthesising", "Completed", "Stopped"
]


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Event(BaseModel):
    seq: int
    investigation_id: str
    type: str
    v: int
    at: str
    actor: Actor
    node_id: str | None = None
    command_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EventDraft(BaseModel):
    type: str
    actor: Actor
    node_id: str | None = None
    command_id: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class UnknownEventType(ValueError):
    pass


class _Data(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


Upcaster = Callable[[dict[str, Any]], dict[str, Any]]

_shapes: dict[str, tuple[int, type[BaseModel]]] = {}
_upcasters: dict[tuple[str, int], Upcaster] = {}


def register_event(type: str, v: int, model: type[BaseModel]) -> None:
    """Register the current shape of `type`'s data."""
    _shapes[type] = (v, model)


def register_upcaster(type: str, from_v: int, fn: Upcaster) -> None:
    """Register `fn` turning data of version `from_v` into version `from_v + 1`."""
    _upcasters[(type, from_v)] = fn


def current_version(type: str) -> int:
    try:
        return _shapes[type][0]
    except KeyError:
        raise UnknownEventType(type) from None


def validate_data(type: str, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    """Validate `data` against the current shape; return (v, normalised data)."""
    try:
        v, model = _shapes[type]
    except KeyError:
        raise UnknownEventType(type) from None
    return v, model.model_validate(data).model_dump(mode="json", by_alias=True)


def upcast(type: str, v: int, data: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    target = current_version(type)
    while v < target:
        data = _upcasters[(type, v)](data)
        v += 1
    return v, data


# --- Phase 1 shapes --------------------------------------------------------------------------


class InvestigationCreated(_Data):
    prompt: str
    settings: dict[str, Any]


class InvestigationStateChanged(_Data):
    from_: InvestigationState | None = Field(alias="from")
    to: InvestigationState
    origin: Origin
    cause: str | None = None
    detail: str | None = None


register_event("investigation.created", 1, InvestigationCreated)
register_event("investigation.state_changed", 1, InvestigationStateChanged)


class SpendRecorded(_Data):
    tier: Literal["strong", "standard", "fast", "verifier"]
    model: str
    amount_usd: str  # decimal string, exact
    approximate: bool
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)


register_event("spend.recorded", 1, SpendRecorded)


# --- Phase 3 shapes --------------------------------------------------------------------------


class RootGoalSet(_Data):
    root_goal: str


class PremiseExtracted(_Data):
    premise_id: str
    text: str
    node_id: str | None = None


class PlanDiff(_Data):
    kept: list[str] = Field(default_factory=list)
    superseded: list[str] = Field(default_factory=list)
    proposed: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PlanVersionCreated(_Data):
    version: int
    instruction_id: str | None = None
    diff: PlanDiff


class PlanReverted(_Data):
    to_version: int
    instruction_id: str


class PlanFailed(_Data):
    reason: str


class PlanDraftRequested(_Data):
    """The (initial) plan is being drafted, the first time or again after plan.failed."""


class NodeProposed(_Data):
    display_id: str
    parent_id: str | None = None
    kind: str
    question: str
    justification: str | None = None
    out_of_scope: str | None = None
    done_when: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    depth: int = 0
    proposed_by: str | None = None


class NodeApproved(_Data):
    budget: dict[str, Any]


class NodeInclusionChanged(_Data):
    node_ids: list[str]
    inclusion: Literal["Included", "Ignored", "Superseded"]
    by: Literal["user", "replan"]
    instruction_id: str | None = None


class InstructionQueued(_Data):
    instruction_id: str
    text: str
    waiting_for: Any = None


class InstructionApplied(_Data):
    instruction_id: str
    at_step: Any = None
    diff: PlanDiff


register_event("investigation.root_goal_set", 1, RootGoalSet)
register_event("premise.extracted", 1, PremiseExtracted)
register_event("plan.version_created", 1, PlanVersionCreated)
register_event("plan.reverted", 1, PlanReverted)
register_event("plan.failed", 1, PlanFailed)
register_event("plan.draft_requested", 1, PlanDraftRequested)
register_event("node.proposed", 1, NodeProposed)
register_event("node.approved", 1, NodeApproved)
register_event("node.inclusion_changed", 1, NodeInclusionChanged)
register_event("instruction.queued", 1, InstructionQueued)
register_event("instruction.applied", 1, InstructionApplied)


# --- Phase 4 shapes: evidence ----------------------------------------------------------------

Credibility = Literal["Primary", "Reputable", "Weak"]
ClaimStatusName = Literal["Confirmed", "Supported", "Unverified", "Contested", "Refuted"]


class SourceRecorded(_Data):
    source_id: str
    url: str
    title: str | None = None
    page_version_id: str
    credibility: Credibility
    published_at: str | None = None
    origin_key: str


class ClaimAdded(_Data):
    claim_id: str
    text: str
    status: ClaimStatusName
    supporting: list[str]
    contradicting: list[str]


class ClaimUpdated(_Data):
    claim_id: str
    status: ClaimStatusName
    supporting: list[str]
    contradicting: list[str]
    merged_into: str | None = None  # set when the claim turned out to be an existing one


class ClaimContradictionRecorded(_Data):
    claim_ids: list[str]


class PremiseOutcome(_Data):
    premise_id: str
    outcome: Literal["confirmed", "refuted", "unverifiable"]


register_event("source.recorded", 1, SourceRecorded)
register_event("claim.added", 1, ClaimAdded)
register_event("claim.updated", 1, ClaimUpdated)
register_event("claim.contradiction_recorded", 1, ClaimContradictionRecorded)
register_event("premise.outcome", 1, PremiseOutcome)


# --- Phase 4 shapes: the node agent loop -----------------------------------------------------

Activity = Literal[
    "Planning", "Searching", "Reading", "Extracting", "Reasoning", "Aggregating",
    "Waiting on children", "Retrying",
]  # fmt: skip
Confidence = Literal["low", "medium", "high"]


class Retry(_Data):
    n: int
    m: int


class NodeStarted(_Data):
    attempt: int
    brief: dict[str, Any]


class NodeActivity(_Data):
    activity: Activity
    detail: str | None = None
    step: str
    retry: Retry | None = None


class NodeStepCompleted(_Data):
    step: str
    kind: str
    summary: str
    route: str | None = None
    page_version_id: str | None = None


class NodeWaitingOnChildren(_Data):
    pass


class Verdict(_Data):
    text: str
    confidence: Confidence


class NodeCompleted(_Data):
    verdict: Verdict
    open_questions: list[str] = Field(default_factory=list)
    off_topic: bool = False


class NodeFailed(_Data):
    reason: str
    auto_retry_used: bool = False


class NodeReset(_Data):
    reason: Literal["recovery", "rerun", "auto_retry", "outage"]
    hint: str | None = None  # auto_retry: the different approach, told in the brief (D-19)


class NodeRejected(_Data):
    reason: str  # "budget", "duplicate", or the reviewer's reason
    duplicate_of: str | None = None


class NodeOffTopic(_Data):
    """The relevance gate found the node's result off-topic: its claims stay out of synthesis
    (E3). A follow-up to node.completed, whose shape stays as the overview gives it."""

    reason: str


class InvestigationConcluding(_Data):
    """The orchestrator decided to conclude; synthesis follows (O3)."""

    cut_short_by: Literal["budget"] | None = None


class AttemptRecord(_Data):
    route: str
    outcome: str
    error: str | None = None


class PageUnobtainable(_Data):
    url: str
    attempts: list[AttemptRecord]


register_event("node.started", 1, NodeStarted)
register_event("node.activity", 1, NodeActivity)
register_event("node.step_completed", 1, NodeStepCompleted)
register_event("node.waiting_on_children", 1, NodeWaitingOnChildren)
register_event("node.completed", 1, NodeCompleted)
register_event("node.failed", 1, NodeFailed)
register_event("node.reset", 1, NodeReset)
register_event("node.rejected", 1, NodeRejected)
register_event("node.off_topic", 1, NodeOffTopic)
register_event("investigation.concluding", 1, InvestigationConcluding)
register_event("page.unobtainable", 1, PageUnobtainable)


# --- Phase 4: runtime ------------------------------------------------------------------------


class ScheduleUpdated(_Data):
    order: list[str]
    reasons: dict[str, str]
    slots: int


class LimitChanged(_Data):
    spending_limit_usd: float


class ReportCreated(_Data):
    report_id: str
    ended_early: bool
    cut_short_by: str | None = None


register_event("schedule.updated", 1, ScheduleUpdated)
register_event("limit.changed", 1, LimitChanged)
register_event("report.created", 1, ReportCreated)
