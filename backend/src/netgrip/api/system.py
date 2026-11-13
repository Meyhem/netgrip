from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from netgrip.api.deps import get_db, get_engine
from netgrip.engine import limiter
from netgrip.engine.engine import Engine
from netgrip.store.db import Database
from netgrip.store.rebuild import rebuild
from netgrip.store.settings import get_settings

router = APIRouter(prefix="/api/system")


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    if path.is_dir():
        return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return 0


@router.get("/pools")
async def pools(engine: Annotated[Engine, Depends(get_engine)]) -> dict:
    settings = await get_settings(engine.db)
    engine.apply_settings(settings)  # settings may have changed since the last look
    cap = settings.capacity
    health = engine.web.health() if engine.web is not None else None
    return {
        "models": {"in_use": limiter.model.in_use, "limit": cap.model_calls},
        "search": {"in_use": limiter.search.in_use, "limit": cap.searches},
        "browsers": {
            "in_use": health.open_pages if health else 0,
            "limit": cap.browser_pages,
            "open": health.browsers if health else 0,
            "restarts_today": health.restarts_today if health else 0,
            "timed_out_today": health.fetches_timed_out_today if health else 0,
        },
        "today_usd": 0,
    }


@router.get("/storage")
async def storage(engine: Annotated[Engine, Depends(get_engine)]) -> dict:
    data_dir = engine.config.data_dir
    count = await engine.db.read("SELECT COUNT(*) FROM investigations")
    pages = await engine.db.read("SELECT COUNT(*) FROM page_versions")
    return {
        # The size on disk, so the per-investigation figures (a shared page counts for each)
        # can sum to more than this (D-21).
        "total_bytes": _size(data_dir),
        "investigations": count[0][0],
        "pages": pages[0][0],
        "data_dir": str(data_dir),
    }


@router.post("/rebuild")
async def rebuild_state(db: Annotated[Database, Depends(get_db)]) -> dict:
    return {"replayed": await rebuild(db)}
