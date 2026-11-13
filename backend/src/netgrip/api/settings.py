from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from netgrip.adapters.model_openai import check_model_key
from netgrip.api.deps import get_db, get_engine
from netgrip.engine import limiter
from netgrip.engine.engine import Engine
from netgrip.engine.estimate import Estimate, estimate
from netgrip.store.db import Database
from netgrip.store.settings import (
    EffortName,
    KeyStatus,
    PresetName,
    Tier,
    get_settings,
    key_status,
    mark_key,
    patch_settings,
    set_key,
)

router = APIRouter(prefix="/api/settings")
estimate_router = APIRouter(prefix="/api/estimate")


async def _response(db: Database, settings=None) -> dict[str, Any]:
    settings = settings or await get_settings(db)
    keys = {name: (await key_status(db, name)).model_dump() for name in ("model", "search")}
    return settings.model_dump(mode="json") | {"keys": keys}


@router.get("")
async def read(db: Annotated[Database, Depends(get_db)]) -> dict:
    return await _response(db)


@router.patch("")
async def patch(
    db: Annotated[Database, Depends(get_db)], partial: Annotated[dict[str, Any], Body()]
) -> dict:
    updated = await patch_settings(db, partial)
    limiter.resize_limiters(updated.capacity)  # the pools follow the new capacity at once
    return await _response(db, updated)


class KeyBody(BaseModel):
    value: str


@router.put("/keys/{name}")
async def put_key(name: str, body: KeyBody, db: Annotated[Database, Depends(get_db)]) -> KeyStatus:
    if name not in ("model", "search"):
        raise HTTPException(404, "No such key")
    await set_key(db, name, body.value)
    return await key_status(db, name)


@router.post("/keys/model/check")
async def check_key(engine: Annotated[Engine, Depends(get_engine)]) -> KeyStatus:
    """Ask the provider whether the stored model key works, and record the verdict."""
    if engine.config.fake:
        return await check_model_key(engine.model_client)
    if not (await key_status(engine.db, "model")).set:
        return await key_status(engine.db, "model")
    status = await check_model_key(engine.model_client)
    await mark_key(engine.db, "model", status.status, status.message)
    return await key_status(engine.db, "model")


class EstimateBody(BaseModel):
    effort: EffortName | None = None
    preset: PresetName | None = None
    tiers: dict[Tier, str] | None = None


@estimate_router.post("")
async def post_estimate(body: EstimateBody, db: Annotated[Database, Depends(get_db)]) -> Estimate:
    s = await get_settings(db)
    tiers = dict(s.presets[body.preset or s.default_preset]) | (body.tiers or {})
    return estimate(s.effort[body.effort or s.default_effort], tiers, s.models)
