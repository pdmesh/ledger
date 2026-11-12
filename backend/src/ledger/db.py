"""Database engine/session helpers and portable column types."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import BigInteger, Engine, Text, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.types import TypeDecorator

MONEY_SCALE = 10_000  # 4 decimal places, exact integer storage on every backend
_Q = Decimal("0.0001")


class Money(TypeDecorator):
    """Exact decimal stored as a scaled integer.

    SQLite has no exact decimal type; storing scaled integers keeps sums exact and keeps
    the schema portable to other databases.
    """

    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> int | None:
        if value is None:
            return None
        d = Decimal(str(value)).quantize(_Q, rounding=ROUND_HALF_EVEN)
        return int(d * MONEY_SCALE)

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return (Decimal(int(value)) / MONEY_SCALE).quantize(_Q)


class JSONText(TypeDecorator):
    """JSON stored as text (portable, readable in any SQLite browser)."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return json.dumps(value, default=str, sort_keys=True)

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        return json.loads(value)


class Base(DeclarativeBase):
    pass


def make_engine(db_path: Path | str) -> Engine:
    url = "sqlite://" if str(db_path) == ":memory:" else f"sqlite:///{db_path}"
    kwargs: dict[str, Any] = {"connect_args": {"check_same_thread": False}}
    if str(db_path) == ":memory:":
        from sqlalchemy.pool import StaticPool

        kwargs["poolclass"] = StaticPool
    engine = create_engine(url, **kwargs)

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn: Any, _rec: Any) -> None:
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    return engine


class Database:
    def __init__(self, db_path: Path | str):
        self.engine = make_engine(db_path)
        self.session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        from ledger import models  # noqa: F401  (register tables)

        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.session_factory()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()
