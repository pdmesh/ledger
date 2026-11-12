from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from ledger.db import Base
from ledger.migrate import upgrade


def test_migrations_match_models(tmp_path):
    db = tmp_path / "m.sqlite3"
    upgrade(db)
    engine = create_engine(f"sqlite:///{db}")
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert diff == [], diff
