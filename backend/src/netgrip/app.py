from contextlib import asynccontextmanager

from fastapi import FastAPI

from netgrip.config import Config


def create_app(config: Config) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config.data_dir.mkdir(parents=True, exist_ok=True)
        yield

    app = FastAPI(title="Netgrip", lifespan=lifespan)
    app.state.config = config

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app
