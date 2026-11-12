"""FastAPI application factory."""

from __future__ import annotations

import logging
import secrets
import shutil
import zipfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ledger.api import analytics, documents, intelligence, people, system, taxonomy, transactions
from ledger.config import seed_defaults
from ledger.db import Database
from ledger.jobs import Worker
from ledger.migrate import upgrade
from ledger.settings import RuntimeSettings

log = logging.getLogger(__name__)

ALLOWED_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _apply_pending_restore(rt: RuntimeSettings) -> None:
    staged = rt.data_dir / "restore-pending.zip"
    if not staged.exists():
        return
    log.warning("applying staged restore from %s", staged)
    with zipfile.ZipFile(staged) as z:
        names = z.namelist()
        if "ledger.sqlite3" not in names:
            staged.unlink()
            return
        for suffix in ("", "-wal", "-shm"):
            p = Path(str(rt.db_path) + suffix)
            if p.exists():
                p.unlink()
        if rt.archive_dir.exists():
            shutil.rmtree(rt.archive_dir)
        rt.archive_dir.mkdir(parents=True)
        for n in names:
            target = (rt.data_dir / n).resolve()
            if rt.data_dir.resolve() not in target.parents:
                continue  # zip-slip guard
            if n.endswith("/"):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(n) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
    staged.unlink()


def create_app(rt: RuntimeSettings | None = None) -> FastAPI:
    rt = rt or RuntimeSettings()
    rt.ensure_dirs()
    _apply_pending_restore(rt)
    upgrade(rt.db_path)
    db = Database(rt.db_path)
    with db.session() as s:
        seed_defaults(s)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker = None
        if rt.start_worker:
            worker = Worker(db, rt)
            worker.start()
            app.state.worker = worker
        yield
        if worker:
            worker.stop()

    app = FastAPI(title="Personal Ledger", version="0.1.0", lifespan=lifespan)
    app.state.db = db
    app.state.rt = rt

    @app.middleware("http")
    async def auth(request: Request, call_next):  # type: ignore[no-untyped-def]
        # The backend binds to loopback only; the per-launch token additionally stops other
        # local processes and web pages from reading the ledger.
        if (
            rt.api_token
            and request.url.path.startswith("/api/")
            and request.url.path != "/api/health"
            and request.method != "OPTIONS"
        ):
            header = request.headers.get("authorization", "")
            token = header.removeprefix("Bearer ").strip() or request.query_params.get("token", "")
            if not secrets.compare_digest(token, rt.api_token):
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    # Added last so it is the outermost layer: every response, including 401s from the auth
    # check above, carries CORS headers, so the UI sees the real error rather than an
    # opaque network failure.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for r in (system, people, taxonomy, documents, transactions, analytics, intelligence):
        app.include_router(r.router, prefix="/api")
    return app
