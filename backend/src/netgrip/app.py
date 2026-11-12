from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from netgrip.api import commands, investigations, settings, stream, system
from netgrip.boundary.bus import EventBus
from netgrip.boundary.commands import CommandRejected
from netgrip.config import Config
from netgrip.engine.engine import Engine
from netgrip.store.db import open_db


def create_app(config: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.data_dir.mkdir(parents=True, exist_ok=True)
        db = await open_db(config.db_path)
        engine = Engine(db, config, EventBus())
        await engine.start()
        app.state.engine = engine
        try:
            yield
        finally:
            await engine.stop()
            await db.close()

    app = FastAPI(title="Netgrip", lifespan=lifespan)
    app.state.config = config

    @app.exception_handler(CommandRejected)
    async def _rejected(request: Request, exc: CommandRejected) -> JSONResponse:
        status = 404 if exc.code == "not_found" else 409
        return JSONResponse({"code": exc.code, "message": exc.message}, status_code=status)

    # Validation errors never echo the input back: it may be a key (D-13).
    @app.exception_handler(ValidationError)
    async def _invalid(request: Request, exc: ValidationError) -> JSONResponse:
        errors = exc.errors(include_url=False, include_input=False, include_context=False)
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{k: e[k] for k in ("type", "loc", "msg") if k in e} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    for module in (investigations, commands, stream, settings, system):
        app.include_router(module.router)

    return app
