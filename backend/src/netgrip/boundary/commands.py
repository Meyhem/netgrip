"""Commands: the only way into the engine (D-02). A repeated client-made id is a no-op."""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Command(BaseModel):
    id: UUID
    type: str
    investigation_id: str
    node_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandAck(BaseModel):
    recorded: bool
    duplicate: bool


class CommandRejected(Exception):
    """The command is not allowed now. Nothing was recorded."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(f"{code}: {message}" if message else code)
        self.code = code
        self.message = message or code.replace("_", " ")
