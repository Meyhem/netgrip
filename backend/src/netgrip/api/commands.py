from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from netgrip.api.deps import get_engine
from netgrip.boundary.commands import Command, CommandAck
from netgrip.engine.engine import Engine

router = APIRouter(prefix="/api/investigations")


class CommandBody(BaseModel):
    id: UUID
    type: str
    node_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


@router.post("/{id}/commands", status_code=202)
async def submit(
    id: str, body: CommandBody, engine: Annotated[Engine, Depends(get_engine)]
) -> CommandAck:
    cmd = Command(
        id=body.id, type=body.type, investigation_id=id, node_id=body.node_id, payload=body.payload
    )
    return await engine.submit(cmd)
