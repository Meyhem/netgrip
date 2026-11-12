from fastapi import Request

from netgrip.engine.engine import Engine
from netgrip.store.db import Database


def get_engine(request: Request) -> Engine:
    return request.app.state.engine


def get_db(request: Request) -> Database:
    return request.app.state.engine.db
