"""Process-level runtime settings (paths, ports, auth token).

These are *not* user configuration. User configuration (locale, identities, taxonomy,
providers, ...) lives in the database and is versioned; see ``ledger.config``.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _default_data_dir() -> Path:
    override = os.environ.get("LEDGER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    home = Path.home()
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "Ledger"
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", home)) / "Ledger"
    return Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share")) / "ledger"


@dataclass
class RuntimeSettings:
    data_dir: Path = field(default_factory=_default_data_dir)
    host: str = "127.0.0.1"
    port: int = int(os.environ.get("LEDGER_PORT", "8765"))
    # When set, every API request must carry ``Authorization: Bearer <token>``.
    # The Tauri shell generates a random token per launch and hands it to both sides.
    api_token: str | None = os.environ.get("LEDGER_API_TOKEN") or None
    start_worker: bool = os.environ.get("LEDGER_DISABLE_WORKER") != "1"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ledger.sqlite3"

    @property
    def archive_dir(self) -> Path:
        return self.data_dir / "archive"

    @property
    def backup_dir(self) -> Path:
        return self.data_dir / "backups"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.archive_dir, self.backup_dir):
            d.mkdir(parents=True, exist_ok=True)
