from __future__ import annotations

from collections.abc import Iterator

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from ledger.db import Database
from ledger.settings import RuntimeSettings


def get_db(request: Request) -> Database:
    return request.app.state.db


def get_rt(request: Request) -> RuntimeSettings:
    return request.app.state.rt


def get_session(request: Request) -> Iterator[Session]:
    db: Database = request.app.state.db
    with db.session() as s:
        yield s


def notify_worker(request: Request) -> None:
    worker = getattr(request.app.state, "worker", None)
    if worker is not None:
        worker.notify()


def not_found(what: str = "resource") -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} not found")


def bad_request(msg: str) -> HTTPException:
    return HTTPException(status_code=400, detail=msg)
