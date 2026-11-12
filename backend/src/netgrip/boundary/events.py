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
