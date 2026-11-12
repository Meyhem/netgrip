"""Live stream: durable events carry their seq as the SSE id; ephemeral messages carry none."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sse_starlette import EventSourceResponse

from netgrip.api.deps import get_engine
from netgrip.boundary.bus import Ephemeral
from netgrip.engine.engine import Engine

router = APIRouter(prefix="/api/investigations")

KEEPALIVE_SECONDS = 15


def _start(last_event_id: str | None, after: int | None) -> int:
    if last_event_id is not None:
        try:
            return max(0, int(last_event_id))
        except ValueError:
            pass
    return max(0, after or 0)


@router.get("/{id}/stream")
async def stream(
    id: str,
    engine: Annotated[Engine, Depends(get_engine)],
    after: Annotated[int | None, Query()] = None,
    last_event_id: Annotated[str | None, Header()] = None,
) -> EventSourceResponse:
    if not await engine.db.read("SELECT 1 FROM investigations WHERE id = ?", [id]):
        raise HTTPException(404, "No such investigation")
    start = _start(last_event_id, after)

    async def messages():
        async for item in engine.subscribe(id, start):
            if isinstance(item, Ephemeral):
                yield {"event": "ephemeral", "data": item.model_dump_json()}
            else:
                yield {"event": "durable", "id": str(item.seq), "data": item.model_dump_json()}

    return EventSourceResponse(messages(), ping=KEEPALIVE_SECONDS)
