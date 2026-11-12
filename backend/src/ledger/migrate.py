"""Schema migrations (Alembic), applied automatically at startup."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def alembic_config(db_path: Path | str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    return cfg


def upgrade(db_path: Path | str, revision: str = "head") -> None:
    command.upgrade(alembic_config(db_path), revision)


def autogenerate(db_path: Path | str, message: str) -> None:
    """Developer helper: ``python -m ledger.migrate "message"`` after changing models."""
    command.upgrade(alembic_config(db_path), "head")
    command.revision(alembic_config(db_path), message=message, autogenerate=True)


if __name__ == "__main__":
    import sys
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        autogenerate(Path(tmp) / "scratch.sqlite3", sys.argv[1] if len(sys.argv) > 1 else "change")
