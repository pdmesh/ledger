"""Watched-folder ingestion (polling; portable and robust to network drives/cloud sync)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ledger.config import get_setting
from ledger.ingestion.extract import SUPPORTED_FORMATS
from ledger.models import Setting
from ledger.settings import RuntimeSettings

INDEX_KEY = "folder_index"


def scan_folder(session: Session, rt: RuntimeSettings) -> dict[str, Any]:
    from ledger.ingestion.service import new_batch, register_file
    from ledger.jobs import enqueue

    ing = get_setting(session, "ingestion")
    folder = ing.get("watch_folder")
    if not folder:
        return {"skipped": "no folder configured"}
    root = Path(folder).expanduser()
    if not root.is_dir():
        return {"error": f"folder not found: {root}"}

    row = session.get(Setting, INDEX_KEY)
    index: dict[str, list[Any]] = dict(row.value) if row and row.value else {}
    batch = None
    queued = duplicates = 0
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith((".", "~$")):
            continue
        if p.suffix.lower() not in SUPPORTED_FORMATS:
            continue
        st = p.stat()
        sig = [st.st_size, int(st.st_mtime)]
        if index.get(str(p), [None, None])[:2] == sig:
            continue
        if batch is None:
            batch = new_batch(session, "folder")
        try:
            res = register_file(session, rt, p, batch=batch, source_path=str(p))
        except Exception as e:  # unsupported/corrupt file: remember it, don't retry forever
            index[str(p)] = [*sig, f"error: {e}"]
            continue
        index[str(p)] = [*sig, res.document.sha256]
        if res.duplicate:
            duplicates += 1
        else:
            enqueue(session, "process_document", {"document_id": res.document.id})
            queued += 1
    if row is None:
        session.add(Setting(key=INDEX_KEY, value=index))
    else:
        row.value = index
    return {"queued": queued, "duplicates": duplicates}
