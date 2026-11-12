"""User configuration access, versioning and first-run seeding."""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ledger import defaults
from ledger.models import (
    Category,
    ClassificationRule,
    ConfigChange,
    ConfigVersion,
    Setting,
)

SCOPES = (
    "general",
    "identities",
    "accounts",
    "taxonomy",
    "merchants",
    "rules",
    "reconciliation",
    "intelligence",
    "ingestion",
)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def get_setting(session: Session, key: str) -> dict[str, Any]:
    row = session.get(Setting, key)
    default = defaults.DEFAULT_SETTINGS.get(key, {})
    return _deep_merge(default, row.value if row else {})


def put_setting(
    session: Session, key: str, value: dict[str, Any], *, summary: str | None = None
) -> dict[str, Any]:
    merged = _deep_merge(get_setting(session, key), value)
    row = session.get(Setting, key)
    if row:
        row.value = merged
    else:
        session.add(Setting(key=key, value=merged))
    bump_version(
        session, key if key in SCOPES else "general", "update", summary or f"{key} updated"
    )
    return merged


def current_version(session: Session, scope: str = "global") -> int:
    row = session.get(ConfigVersion, scope)
    return row.version if row else 0


def bump_version(
    session: Session,
    scope: str,
    action: str,
    summary: str,
    *,
    detail: dict[str, Any] | None = None,
    propagation: str = "none",
) -> int:
    """Increment scope and global versions and record the change. Returns global version."""
    versions = {}
    for s in (scope, "global"):
        row = session.get(ConfigVersion, s)
        if row is None:
            row = ConfigVersion(scope=s, version=0)
            session.add(row)
        row.version += 1
        versions[s] = row.version
    session.add(
        ConfigChange(
            scope=scope,
            version=versions[scope],
            global_version=versions["global"],
            action=action,
            summary=summary,
            detail=detail,
            propagation=propagation,
        )
    )
    session.flush()
    return versions["global"]


def seed_defaults(session: Session) -> None:
    """Idempotently seed taxonomy and system rules on first run."""
    if session.scalar(select(Category.id).limit(1)) is None:
        order = 0
        for root in defaults.DEFAULT_TAXONOMY:
            order += 1
            r = Category(
                slug=root["slug"],
                name=root["name"],
                description=root["description"],
                role=root["role"],
                is_system=True,
                sort_order=order,
            )
            session.add(r)
            session.flush()
            for i, (slug, name, desc) in enumerate(root["children"]):
                session.add(
                    Category(
                        slug=slug,
                        name=name,
                        description=desc,
                        parent_id=r.id,
                        role=root["role"],
                        is_system=slug in (defaults.FALLBACK_INFLOW, defaults.FALLBACK_OUTFLOW),
                        sort_order=i,
                    )
                )
        bump_version(session, "taxonomy", "seed", "Default taxonomy installed")

    if session.scalar(select(ClassificationRule.id).limit(1)) is None:
        for rule in defaults.DEFAULT_RULES:
            session.add(ClassificationRule(**rule))
        bump_version(session, "rules", "seed", "Default classification rules installed")
    session.flush()
