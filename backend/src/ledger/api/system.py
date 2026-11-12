from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger import defaults
from ledger.api.deps import bad_request, get_rt, get_session, not_found, notify_worker
from ledger.config import current_version, get_setting, put_setting
from ledger.jobs import enqueue
from ledger.models import ConfigChange, FxRate, Job
from ledger.settings import RuntimeSettings

router = APIRouter(tags=["system"])

EDITABLE_SETTINGS = ("general", "ingestion", "reconciliation")


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True}


@router.get("/settings")
def all_settings(s: Session = Depends(get_session)) -> dict[str, Any]:
    out = {k: get_setting(s, k) for k in EDITABLE_SETTINGS}
    out["config_version"] = current_version(s)
    return out


@router.put("/settings/{key}")
def update_settings(
    key: str, body: dict[str, Any], request: Request, s: Session = Depends(get_session)
) -> dict[str, Any]:
    if key not in EDITABLE_SETTINGS:
        raise bad_request(f"unknown settings group {key}")
    before = get_setting(s, key)
    merged = put_setting(s, key, body)
    if key == "general" and before.get("base_currency") != merged.get("base_currency"):
        enqueue(s, "recompute_fx", {}, dedupe_key="recompute_fx")
    if key == "ingestion" and merged.get("watch_enabled"):
        enqueue(s, "scan_folder", {}, dedupe_key="scan_folder")
    s.flush()
    notify_worker(request)
    return merged


@router.get("/onboarding/presets")
def presets() -> dict[str, Any]:
    return {"countries": defaults.COUNTRY_PRESETS}


class OnboardingBody(BaseModel):
    country: str | None = None
    base_currency: str
    locale: str = "en"
    timezone: str | None = None
    date_format: str | None = None


@router.post("/onboarding")
def complete_onboarding(body: OnboardingBody, s: Session = Depends(get_session)) -> dict[str, Any]:
    preset = defaults.COUNTRY_PRESETS.get((body.country or "").upper(), {})
    values: dict[str, Any] = {**preset, **{k: v for k, v in body.model_dump().items() if v}}
    values["base_currency"] = body.base_currency.upper()
    values["onboarding_complete"] = True
    return put_setting(s, "general", values, summary="Onboarding completed")


@router.get("/config/history")
def config_history(limit: int = 100, s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = s.scalars(select(ConfigChange).order_by(ConfigChange.id.desc()).limit(limit)).all()
    return [
        {
            "id": c.id,
            "scope": c.scope,
            "version": c.version,
            "global_version": c.global_version,
            "action": c.action,
            "summary": c.summary,
            "propagation": c.propagation,
            "created_at": c.created_at,
        }
        for c in rows
    ]


@router.get("/jobs")
def jobs(limit: int = 50, s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    rows = s.scalars(select(Job).order_by(Job.id.desc()).limit(limit)).all()
    return [
        {
            "id": j.id,
            "kind": j.kind,
            "status": j.status,
            "attempts": j.attempts,
            "error": (j.error or "").splitlines()[0] if j.error else None,
            "result": j.result,
            "created_at": j.created_at,
            "finished_at": j.finished_at,
            "payload": j.payload,
        }
        for j in rows
    ]


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, request: Request, s: Session = Depends(get_session)) -> dict[str, Any]:
    j = s.get(Job, job_id)
    if j is None:
        raise not_found("job")
    j.status, j.attempts, j.error = "queued", 0, None
    notify_worker(request)
    return {"ok": True}


# -- FX rates (manual/imported historical rates) -------------------------------------------


class FxBody(BaseModel):
    rate_date: str
    from_currency: str
    to_currency: str
    rate: str


@router.get("/fx-rates")
def fx_rates(s: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "rate_date": r.rate_date,
            "from_currency": r.from_currency,
            "to_currency": r.to_currency,
            "rate": str(r.rate),
            "source": r.source,
        }
        for r in s.scalars(select(FxRate).order_by(FxRate.rate_date.desc())).all()
    ]


@router.post("/fx-rates")
def add_fx_rate(body: FxBody, request: Request, s: Session = Depends(get_session)) -> dict:
    from datetime import date
    from decimal import Decimal

    r = FxRate(
        rate_date=date.fromisoformat(body.rate_date),
        from_currency=body.from_currency.upper(),
        to_currency=body.to_currency.upper(),
        rate=Decimal(body.rate),
    )
    s.add(r)
    s.flush()
    enqueue(s, "recompute_fx", {}, dedupe_key="recompute_fx")
    notify_worker(request)
    return {"id": r.id}


# -- Backup ------------------------------------------------------------------------------


@router.post("/backup")
def create_backup(rt: RuntimeSettings = Depends(get_rt)) -> dict[str, Any]:
    """Consistent snapshot of the database plus the document archive as a zip."""
    rt.ensure_dirs()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap = rt.backup_dir / f"ledger-{stamp}.sqlite3"
    src = sqlite3.connect(rt.db_path)
    dst = sqlite3.connect(snap)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    out = rt.backup_dir / f"ledger-backup-{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(snap, "ledger.sqlite3")
        for p in rt.archive_dir.rglob("*"):
            if p.is_file():
                z.write(p, f"archive/{p.relative_to(rt.archive_dir)}")
    snap.unlink()
    return {"path": str(out), "name": out.name, "size_bytes": out.stat().st_size}


@router.get("/backup/{name}")
def download_backup(name: str, rt: RuntimeSettings = Depends(get_rt)) -> FileResponse:
    p = (rt.backup_dir / name).resolve()
    if p.parent != rt.backup_dir.resolve() or not p.exists():
        raise not_found("backup")
    return FileResponse(p, filename=name)


@router.post("/restore")
def restore_backup(body: dict[str, str], rt: RuntimeSettings = Depends(get_rt)) -> dict:
    """Stage a restore; it is applied on next start (the DB is in use while running)."""
    name = body.get("name", "")
    p = (rt.backup_dir / name).resolve()
    if p.parent != rt.backup_dir.resolve() or not p.exists():
        raise not_found("backup")
    staged = rt.data_dir / "restore-pending.zip"
    shutil.copy2(p, staged)
    return {"staged": True, "message": "Restart the application to complete the restore."}
