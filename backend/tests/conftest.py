from __future__ import annotations

from pathlib import Path

import pytest

from ledger.config import put_setting, seed_defaults
from ledger.db import Database
from ledger.models import Identity, IdentityAlias, Institution
from ledger.settings import RuntimeSettings
from ledger.text import normalize_name

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def rt(tmp_path: Path) -> RuntimeSettings:
    r = RuntimeSettings(data_dir=tmp_path / "data", start_worker=False)
    r.ensure_dirs()
    return r


@pytest.fixture
def db(rt: RuntimeSettings) -> Database:
    d = Database(rt.db_path)
    d.create_all()
    with d.session() as s:
        seed_defaults(s)
    return d


@pytest.fixture
def household(db: Database) -> dict[str, int]:
    """Two fictional household members and three fictional institutions."""
    with db.session() as s:
        put_setting(s, "general", {"country": "IN", "base_currency": "INR", "date_format": "DMY"})
        ids = {}
        for name, aliases in (
            ("Alex Sample", ["A Sample", "Alex S"]),
            ("Sam Sample", ["S Sample"]),
        ):
            ident = Identity(display_name=name, legal_name=name)
            for a in aliases:
                ident.aliases.append(IdentityAlias(alias=a, normalized=normalize_name(a)))
            s.add(ident)
            s.flush()
            ids[name] = ident.id
        for inst, aliases in (
            ("Northwind Bank", []),
            ("Contoso Bank", []),
            ("Fabrikam Card", ["fabrikam"]),
        ):
            s.add(Institution(name=inst, aliases=aliases))
    return ids
