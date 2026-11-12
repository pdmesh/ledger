"""Persistent local job queue with a single background worker thread.

Jobs live in SQLite, so work queued before a crash or quit resumes on the next launch.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ledger.models import Job, utcnow

if TYPE_CHECKING:
    from ledger.db import Database
    from ledger.settings import RuntimeSettings

log = logging.getLogger(__name__)

Handler = Callable[[Session, "RuntimeSettings", dict[str, Any]], dict[str, Any] | None]


def enqueue(
    session: Session,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe_key: str | None = None,
) -> Job:
    """Queue a job. A queued job with the same ``dedupe_key`` is reused (coalescing)."""
    if dedupe_key:
        existing = session.scalar(
            select(Job).where(Job.dedupe_key == dedupe_key, Job.status == "queued")
        )
        if existing:
            return existing
    job = Job(kind=kind, payload=payload or {}, dedupe_key=dedupe_key)
    session.add(job)
    session.flush()
    return job


def _handlers() -> dict[str, Handler]:
    from ledger import propagation
    from ledger.ingestion import folder
    from ledger.ingestion.service import process_document
    from ledger.models import Document
    from ledger.reconciliation.engine import Reconciler

    def h_process(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        doc = s.get(Document, p["document_id"])
        if doc is None:
            return {"skipped": "document deleted"}
        return process_document(s, rt, doc)

    def h_reclassify(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        n = propagation.reclassify(s, p, use_ai=bool(p.get("use_ai")))
        return {"reclassified": n}

    def h_reconcile(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        return Reconciler(s).run()

    def h_remap(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        return {"remapped": propagation.remap_merchants(s)}

    def h_owners(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        return {"matches": propagation.resolve_all_owners(s)}

    def h_scan(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        return folder.scan_folder(s, rt)

    def h_fx(s: Session, rt: RuntimeSettings, p: dict[str, Any]) -> dict[str, Any]:
        from ledger.fx import recompute_all

        return {"recomputed": recompute_all(s)}

    return {
        "process_document": h_process,
        "reclassify": h_reclassify,
        "reconcile": h_reconcile,
        "remap_merchants": h_remap,
        "resolve_owners": h_owners,
        "scan_folder": h_scan,
        "recompute_fx": h_fx,
    }


def run_one(db: Database, rt: RuntimeSettings) -> bool:
    """Claim and run the oldest queued job. Returns False when the queue is empty."""
    with db.session() as s:
        job = s.scalar(select(Job).where(Job.status == "queued").order_by(Job.id).limit(1))
        if job is None:
            return False
        claimed = s.execute(
            update(Job)
            .where(Job.id == job.id, Job.status == "queued")
            .values(status="running", started_at=utcnow(), attempts=Job.attempts + 1)
        ).rowcount
        if not claimed:
            return True
        job_id, kind, payload = job.id, job.kind, dict(job.payload or {})

    handler = _handlers().get(kind)
    try:
        if handler is None:
            raise RuntimeError(f"no handler for job kind '{kind}'")
        with db.session() as s:
            result = handler(s, rt, payload) or {}
        with db.session() as s:
            j = s.get(Job, job_id)
            j.status, j.result, j.error, j.finished_at = "done", result, None, utcnow()
    except Exception as e:  # noqa: BLE001 - jobs must never kill the worker
        log.error("job %s (%s) failed: %s", job_id, kind, e)
        with db.session() as s:
            j = s.get(Job, job_id)
            j.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()[-2000:]}"
            j.finished_at = utcnow()
            j.status = "queued" if j.attempts < j.max_attempts else "failed"
            if kind == "process_document" and j.status == "failed":
                from ledger.models import Document

                doc = s.get(Document, payload.get("document_id"))
                if doc is not None:
                    doc.status, doc.error = "failed", str(e)[:1000]
    return True


def run_pending(db: Database, rt: RuntimeSettings, limit: int = 1000) -> int:
    n = 0
    while n < limit and run_one(db, rt):
        n += 1
    return n


class Worker:
    def __init__(self, db: Database, rt: RuntimeSettings):
        self.db = db
        self.rt = rt
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_scan = 0.0

    def start(self) -> None:
        with self.db.session() as s:
            # resume work interrupted by a crash or quit
            s.execute(update(Job).where(Job.status == "running").values(status="queued"))
        self._thread = threading.Thread(target=self._loop, name="ledger-worker", daemon=True)
        self._thread.start()

    def notify(self) -> None:
        self._wake.set()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _maybe_scan_folder(self) -> None:
        from ledger.config import get_setting

        with self.db.session() as s:
            ing = get_setting(s, "ingestion")
            if not ing.get("watch_enabled") or not ing.get("watch_folder"):
                return
            if time.monotonic() - self._last_scan < max(5, int(ing.get("poll_seconds", 30))):
                return
            self._last_scan = time.monotonic()
            enqueue(s, "scan_folder", {}, dedupe_key="scan_folder")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self._maybe_scan_folder()
                worked = run_one(self.db, self.rt)
            except Exception:  # pragma: no cover
                log.exception("worker loop error")
                worked = False
            if not worked:
                self._wake.wait(timeout=2.0)
                self._wake.clear()
