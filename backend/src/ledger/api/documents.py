"""Import Centre: uploads, folder ingestion, document inspection and deletion."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import case, delete, func, select, update
from sqlalchemy.orm import Session

from ledger import desktop
from ledger.api import serializers as ser
from ledger.api.deps import bad_request, get_rt, get_session, not_found, notify_worker
from ledger.ingestion import passwords
from ledger.ingestion.extract import ExtractionError
from ledger.ingestion.service import new_batch, register_file
from ledger.jobs import enqueue
from ledger.models import Document, Job, ReconciliationLink, Transaction
from ledger.settings import RuntimeSettings

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 100 * 1024 * 1024


@router.post("/documents")
async def upload_documents(
    request: Request,
    files: list[UploadFile] = File(...),
    s: Session = Depends(get_session),
    rt: RuntimeSettings = Depends(get_rt),
) -> dict[str, Any]:
    batch = new_batch(s, "manual")
    results = []
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            name = Path(f.filename or "upload").name
            dest = Path(tmp) / name
            size = 0
            with dest.open("wb") as out:
                while chunk := await f.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise bad_request(f"{name} exceeds the upload size limit")
                    out.write(chunk)
            try:
                res = register_file(s, rt, dest, original_name=name, batch=batch)
            except ExtractionError as e:
                results.append({"filename": name, "status": "rejected", "error": str(e)})
                continue
            if not res.duplicate:
                enqueue(s, "process_document", {"document_id": res.document.id})
            results.append(
                {
                    "filename": name,
                    "document_id": res.document.id,
                    "status": "duplicate" if res.duplicate else "queued",
                }
            )
    s.flush()
    notify_worker(request)
    return {"batch_id": batch.id, "results": results}


@router.post("/documents/import-path")
def import_path(
    body: dict[str, str],
    request: Request,
    s: Session = Depends(get_session),
    rt: RuntimeSettings = Depends(get_rt),
) -> dict[str, Any]:
    """Import a local file by path (used by the desktop shell's native file picker)."""
    p = Path(body.get("path", "")).expanduser()
    if not p.is_file():
        raise bad_request("file not found")
    try:
        res = register_file(s, rt, p, batch=new_batch(s, "manual"), source_path=str(p))
    except ExtractionError as e:
        raise bad_request(str(e)) from e
    if not res.duplicate:
        enqueue(s, "process_document", {"document_id": res.document.id})
    notify_worker(request)
    return {"document_id": res.document.id, "status": "duplicate" if res.duplicate else "queued"}


@router.post("/documents/scan-folder")
def scan_now(request: Request, s: Session = Depends(get_session)) -> dict[str, Any]:
    job = enqueue(s, "scan_folder", {}, dedupe_key="scan_folder")
    notify_worker(request)
    return {"job_id": job.id}


@router.get("/documents")
def list_documents(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    docs = s.scalars(select(Document).order_by(Document.id.desc())).all()
    amt = Transaction.amount
    # Live in/out totals per statement (every row it produced, duplicates included), in the
    # statement's own currency, so a card statement's outflow can be checked against the bill.
    totals = {
        d: (i, o, n)
        for d, i, o, n in s.execute(
            select(
                Transaction.document_id,
                func.sum(case((amt > 0, amt), else_=0)),
                func.sum(case((amt < 0, amt), else_=0)),
                func.count(),
            )
            .where(Transaction.document_id.is_not(None))
            .group_by(Transaction.document_id)
        ).all()
    }
    q = Decimal("0.01")
    out = []
    for d in docs:
        row = ser.document(d)
        i, o, n = totals.get(d.id, (None, None, 0))
        row["totals"] = {
            "inflow": str(Decimal(i or 0).quantize(q)),
            "outflow": str(Decimal(o or 0).quantize(q)),
            "count": n,
        }
        out.append(row)
    return out


@router.get("/documents/summary")
def import_summary(s: Session = Depends(get_session)) -> dict[str, Any]:
    by_status = dict(
        s.execute(select(Document.status, func.count()).group_by(Document.status)).all()
    )
    links = dict(
        s.execute(
            select(ReconciliationLink.kind, func.count())
            .where(ReconciliationLink.status != "rejected")
            .group_by(ReconciliationLink.kind)
        ).all()
    )
    pending = s.scalar(
        select(func.count()).select_from(Job).where(Job.status.in_(("queued", "running")))
    )
    return {"documents": by_status, "reconciliation": links, "pending_jobs": pending}


@router.get("/documents/{doc_id}")
def get_document(doc_id: int, s: Session = Depends(get_session)) -> dict[str, Any]:
    d = s.get(Document, doc_id)
    if d is None:
        raise not_found("document")
    out = ser.document(d)
    txns = s.scalars(
        select(Transaction).where(Transaction.document_id == d.id).order_by(Transaction.id)
    ).all()
    out["transactions"] = [ser.transaction(t) for t in txns]
    return out


@router.get("/documents/{doc_id}/file")
def document_file(
    doc_id: int, s: Session = Depends(get_session), rt: RuntimeSettings = Depends(get_rt)
) -> FileResponse:
    d = s.get(Document, doc_id)
    if d is None:
        raise not_found("document")
    path = (rt.data_dir / d.archive_path).resolve()
    if rt.data_dir.resolve() not in path.parents or not path.exists():
        raise not_found("file")
    return FileResponse(path, filename=d.original_filename)


@router.post("/documents/{doc_id}/open")
def open_document(
    doc_id: int, s: Session = Depends(get_session), rt: RuntimeSettings = Depends(get_rt)
) -> dict[str, Any]:
    """Open the archived original in the OS's default viewer."""
    d = s.get(Document, doc_id)
    if d is None:
        raise not_found("document")
    path = (rt.data_dir / d.archive_path).resolve()
    if rt.data_dir.resolve() not in path.parents:
        raise not_found("file")
    # Only hand document types to the OS (older archives kept the upload's own extension).
    if path.suffix.lower() not in desktop.OPENABLE_SUFFIXES:
        raise bad_request(f"won't open a '{path.suffix}' file; use Re-process or delete it")
    try:
        desktop.open_path(path)
    except desktop.OpenError as e:
        raise bad_request(str(e)) from e
    return {"ok": True}


class PasswordBody(BaseModel):
    password: str
    remember: bool = True


@router.post("/documents/{doc_id}/password")
def unlock(
    doc_id: int,
    body: PasswordBody,
    request: Request,
    s: Session = Depends(get_session),
    rt: RuntimeSettings = Depends(get_rt),
) -> dict[str, Any]:
    """Check a PDF password now, keep it in the OS keychain and import the statement.

    The password is never written to the database, the job queue or the logs.
    """
    d = s.get(Document, doc_id)
    if d is None:
        raise not_found("document")
    if d.file_format != "pdf" or d.status != "needs_password":
        raise bad_request("this document isn't waiting for a password")
    if not passwords.opens_with(rt.data_dir / d.archive_path, body.password):
        raise bad_request("That password doesn't open this PDF")
    stored = passwords.set_document_password(d.sha256, body.password)
    if body.remember:
        passwords.remember_password(body.password)
    d.status, d.error = "queued", None
    enqueue(s, "process_document", {"document_id": d.id})
    # Other locked statements often share the password; give them another try.
    retried = 0
    if body.remember:
        for other in s.scalars(
            select(Document).where(Document.status == "needs_password", Document.id != d.id)
        ):
            other.status, other.error = "queued", None
            enqueue(s, "process_document", {"document_id": other.id})
            retried += 1
    notify_worker(request)
    return {"ok": True, "stored_in_keychain": stored, "retried_others": retried}


@router.post("/documents/{doc_id}/reprocess")
def reprocess(doc_id: int, request: Request, s: Session = Depends(get_session)) -> dict[str, Any]:
    d = s.get(Document, doc_id)
    if d is None:
        raise not_found("document")
    # user corrections on this document's rows would be lost; refuse if any exist
    pinned = [
        t
        for t in s.scalars(select(Transaction).where(Transaction.document_id == d.id))
        if t.pinned_fields
    ]
    if pinned:
        raise bad_request("document has user-corrected transactions; delete it to re-import")
    s.execute(delete(Transaction).where(Transaction.document_id == d.id))
    d.status = "queued"
    enqueue(s, "process_document", {"document_id": d.id})
    notify_worker(request)
    return {"ok": True}


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    request: Request,
    s: Session = Depends(get_session),
    rt: RuntimeSettings = Depends(get_rt),
) -> dict[str, Any]:
    """Delete a document, its archived file and every transaction extracted from it."""
    d = s.get(Document, doc_id)
    if d is None:
        raise not_found("document")
    ids = list(s.scalars(select(Transaction.id).where(Transaction.document_id == d.id)))
    # rows elsewhere that were flagged as duplicates of these become live again
    if ids:
        s.execute(
            update(Transaction)
            .where(Transaction.duplicate_of_id.in_(ids))
            .values(duplicate_of_id=None)
        )
        s.execute(delete(Transaction).where(Transaction.id.in_(ids)))
    archive = rt.data_dir / d.archive_path
    s.delete(d)
    s.flush()
    if archive.exists():
        archive.unlink()
    enqueue(s, "reconcile", {}, dedupe_key="reconcile")
    notify_worker(request)
    return {"deleted_transactions": len(ids)}
