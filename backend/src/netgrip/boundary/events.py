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
