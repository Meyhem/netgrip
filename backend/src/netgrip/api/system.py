from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from netgrip.api.deps import get_db, get_engine
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
async def pools(db: Annotated[Database, Depends(get_db)]) -> dict:
    cap = (await get_settings(db)).capacity
    return {
        "models": {"in_use": 0, "limit": cap.model_calls},
        "search": {"in_use": 0, "limit": cap.searches},
        "browsers": {"in_use": 0, "limit": cap.browser_pages},
        "today_usd": 0,
    }


@router.get("/storage")
async def storage(engine: Annotated[Engine, Depends(get_engine)]) -> dict:
    data_dir = engine.config.data_dir
    count = await engine.db.read("SELECT COUNT(*) FROM investigations")
    return {
        "total_bytes": _size(data_dir),
        "investigations": count[0][0],
        "pages": 0,
        "data_dir": str(data_dir),
    }


@router.post("/rebuild")
async def rebuild_state(db: Annotated[Database, Depends(get_db)]) -> dict:
    return {"replayed": await rebuild(db)}
