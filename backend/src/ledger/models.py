"""Persistent domain model.

Two broad areas:

* **Configuration** (identities, accounts, taxonomy, merchants, rules, settings) -- the
  user's financial context. Versioned via ``ConfigVersion``/``ConfigChange``.
* **Ledger** (documents, transactions, reconciliation links, classification history,
  AI execution records) -- derived from imported documents and user corrections.

Original extracted values are never overwritten by derived/AI values: transactions keep
``description_raw`` and ``source_ref`` alongside normalized fields, and every
classification/override is appended to a history table.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ledger.db import Base, JSONText, Money


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------------------
# Settings & configuration versioning
# --------------------------------------------------------------------------------------


class Setting(Base):
    """Key/value user settings (locale, currency, intelligence routing, folder watch...)."""

    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONText)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ConfigVersion(Base):
    """Monotonic version counter per configuration scope (plus a ``global`` scope)."""

    __tablename__ = "config_versions"
    scope: Mapped[str] = mapped_column(String(50), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ConfigChange(Base):
    """Audit log of configuration changes and how they were propagated."""

    __tablename__ = "config_changes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(50))
    version: Mapped[int] = mapped_column(Integer)
    global_version: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(50))
    summary: Mapped[str] = mapped_column(Text)
    detail: Mapped[Any] = mapped_column(JSONText, nullable=True)
    propagation: Mapped[str] = mapped_column(String(20), default="none")  # none|deterministic|ai
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# --------------------------------------------------------------------------------------
# Identities, institutions & accounts
# --------------------------------------------------------------------------------------


class Identity(TimestampMixin, Base):
    __tablename__ = "identities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(200))
    legal_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default="individual")  # individual|household
    identifiers: Mapped[list[str]] = mapped_column(JSONText, default=list)  # emails, customer ids
    aliases: Mapped[list[IdentityAlias]] = relationship(
        back_populates="identity", cascade="all, delete-orphan", lazy="selectin"
    )


class IdentityAlias(Base):
    __tablename__ = "identity_aliases"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    identity_id: Mapped[int] = mapped_column(ForeignKey("identities.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(300))
    normalized: Mapped[str] = mapped_column(String(300), index=True)
    identity: Mapped[Identity] = relationship(back_populates="aliases")


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    aliases: Mapped[list[str]] = mapped_column(JSONText, default=list)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)


class AccountOwner(Base):
    __tablename__ = "account_owners"
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True
    )
    identity_id: Mapped[int] = mapped_column(
        ForeignKey("identities.id", ondelete="CASCADE"), primary_key=True
    )
    # how ownership was established: user|document_header|alias_match|inferred
    source: Mapped[str] = mapped_column(String(30), default="user")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)


ACCOUNT_TYPES = (
    "savings",
    "current",
    "credit_card",
    "investment",
    "brokerage",
    "fixed_deposit",
    "loan",
    "cash",
    "other",
)


class Account(TimestampMixin, Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    account_type: Mapped[str] = mapped_column(String(30), default="other")
    # Only the last 4 digits are stored; full numbers are never persisted.
    masked_number: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    currency: Mapped[str] = mapped_column(String(3))
    aliases: Mapped[list[str]] = mapped_column(JSONText, default=list)
    statement_metadata: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    auto_discovered: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    institution: Mapped[Institution | None] = relationship(lazy="joined")
    owners: Mapped[list[AccountOwner]] = relationship(cascade="all, delete-orphan", lazy="selectin")


# --------------------------------------------------------------------------------------
# Taxonomy, merchants & rules
# --------------------------------------------------------------------------------------

# Analytic roles are the only hardcoded part of the taxonomy. Every category inherits the
# role of its root; analytics are computed from roles, so users can freely add, rename,
# move and merge categories without breaking metrics.
ROLES = ("income", "expense", "investment", "transfer", "adjustment")


class Category(TimestampMixin, Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20))  # denormalized from root; kept in sync
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # Bumped when the *meaning* (description/role) changes -> triggers reclassification
    semantic_version: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)


class Merchant(TimestampMixin, Base):
    __tablename__ = "merchants"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(200))
    key: Mapped[str] = mapped_column(String(200), unique=True)  # normalized canonical key
    description: Mapped[str] = mapped_column(Text, default="")
    default_category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    # user|auto|llm -- user-defined mappings take precedence over everything but overrides
    source: Mapped[str] = mapped_column(String(20), default="auto")
    aliases: Mapped[list[MerchantAlias]] = relationship(
        back_populates="merchant", cascade="all, delete-orphan", lazy="selectin"
    )


class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"
    __table_args__ = (UniqueConstraint("pattern", "match_type"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    merchant_id: Mapped[int] = mapped_column(ForeignKey("merchants.id", ondelete="CASCADE"))
    pattern: Mapped[str] = mapped_column(String(300))  # normalized
    match_type: Mapped[str] = mapped_column(String(20), default="key")  # key|contains|regex
    source: Mapped[str] = mapped_column(String(20), default="auto")
    merchant: Mapped[Merchant] = relationship(back_populates="aliases")


class ClassificationRule(TimestampMixin, Base):
    """Deterministic rule: if ``conditions`` match, apply ``actions``.

    conditions: {"description_contains": [..], "description_regex": "...",
                 "direction": "inflow|outflow", "account_ids": [..], "account_types": [..],
                 "min_amount": "..", "max_amount": ".."}
    actions:    {"category": "<slug>", "merchant_id": 1, "owner_identity_id": 2}
    """

    __tablename__ = "classification_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower runs first
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    actions: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    source: Mapped[str] = mapped_column(String(20), default="user")  # user|system|learned
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("rate_date", "from_currency", "to_currency"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rate_date: Mapped[date] = mapped_column(Date)
    from_currency: Mapped[str] = mapped_column(String(3))
    to_currency: Mapped[str] = mapped_column(String(3))
    rate: Mapped[Decimal] = mapped_column(Money)
    source: Mapped[str] = mapped_column(String(30), default="user")


# --------------------------------------------------------------------------------------
# Documents & imports
# --------------------------------------------------------------------------------------


class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))  # manual|folder|api
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Document(TimestampMixin, Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL"), nullable=True
    )
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    original_filename: Mapped[str] = mapped_column(String(500))
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)  # for folder imports
    archive_path: Mapped[str] = mapped_column(Text)
    file_format: Mapped[str] = mapped_column(String(10))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # queued|processing|processed|failed|duplicate
    status: Mapped[str] = mapped_column(String(20), default="queued")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSONText, default=list)

    institution_id: Mapped[int | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    document_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    statement_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    statement_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    opening_balance: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    closing_balance: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    # identification evidence: detected institution text, holder names, method, etc.
    identification: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    extraction_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    stats: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    account: Mapped[Account | None] = relationship(lazy="joined")
    institution: Mapped[Institution | None] = relationship(lazy="joined")


# --------------------------------------------------------------------------------------
# Ledger
# --------------------------------------------------------------------------------------


class Transaction(TimestampMixin, Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_txn_account_date", "account_id", "txn_date"),
        Index("ix_txn_date", "txn_date"),
        Index("ix_txn_category", "category_id"),
        Index("ix_txn_merchant", "merchant_id"),
        Index("ix_txn_fingerprint", "fingerprint"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=True
    )
    # provenance within the source document: {"page": 2, "row": 14, "table": 0}
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    entry_method: Mapped[str] = mapped_column(String(20), default="import")  # import|manual

    txn_date: Mapped[date] = mapped_column(Date)
    posting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description_raw: Mapped[str] = mapped_column(Text)
    description_normalized: Mapped[str] = mapped_column(Text, default="")
    # Signed: positive = inflow to the account, negative = outflow.
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    direction: Mapped[str] = mapped_column(String(10))  # inflow|outflow
    base_amount: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    fx_rate: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    reference: Mapped[str | None] = mapped_column(String(200), nullable=True)
    balance_after: Mapped[Decimal | None] = mapped_column(Money, nullable=True)
    raw: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)  # extracted cell values

    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id", ondelete="SET NULL"), nullable=True
    )
    merchant_id: Mapped[int | None] = mapped_column(
        ForeignKey("merchants.id", ondelete="SET NULL"), nullable=True
    )
    # Explicit per-transaction attribution; NULL means "the account's owners".
    owner_identity_id: Mapped[int | None] = mapped_column(
        ForeignKey("identities.id", ondelete="SET NULL"), nullable=True
    )
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False)

    classification_method: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_evidence: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    classification_config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Fields pinned by the user; never overwritten by automated processing.
    pinned_fields: Mapped[list[str]] = mapped_column(JSONText, default=list)

    fingerprint: Mapped[str] = mapped_column(String(64))
    duplicate_of_id: Mapped[int | None] = mapped_column(
        ForeignKey("transactions.id", ondelete="SET NULL"), nullable=True
    )

    account: Mapped[Account] = relationship(lazy="joined")
    category: Mapped[Category | None] = relationship(lazy="joined")
    merchant: Mapped[Merchant | None] = relationship(lazy="joined", foreign_keys=[merchant_id])
    document: Mapped[Document | None] = relationship(lazy="select")


class TransactionOverride(Base):
    """User corrections, recorded separately from automated decisions."""

    __tablename__ = "transaction_overrides"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    field: Mapped[str] = mapped_column(String(50))
    old_value: Mapped[Any] = mapped_column(JSONText, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSONText, nullable=True)
    apply_to_similar: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ClassificationRecord(Base):
    """Append-only history of every classification decision applied to a transaction."""

    __tablename__ = "classification_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    method: Mapped[str] = mapped_column(String(20))
    category_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    merchant_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    ai_execution_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


LINK_KINDS = ("internal_transfer", "card_settlement", "refund", "duplicate")


class ReconciliationLink(Base):
    """A relationship between two transactions. Never deletes either side."""

    __tablename__ = "reconciliation_links"
    __table_args__ = (UniqueConstraint("kind", "from_transaction_id", "to_transaction_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(30))
    # from = the outflow / original / earlier record; to = inflow / refund / duplicate
    from_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    to_transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id", ondelete="CASCADE"), index=True
    )
    confidence: Mapped[float] = mapped_column(Float)
    method: Mapped[str] = mapped_column(String(20))  # deterministic|llm|user
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="auto")  # auto|confirmed|rejected
    history: Mapped[list[dict[str, Any]]] = mapped_column(JSONText, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# --------------------------------------------------------------------------------------
# Intelligence & jobs
# --------------------------------------------------------------------------------------


class AIExecution(Base):
    __tablename__ = "ai_executions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task: Mapped[str] = mapped_column(String(50))
    provider_id: Mapped[str] = mapped_column(String(100))
    provider_kind: Mapped[str] = mapped_column(String(20))
    model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20))  # ok|error|invalid_output
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_sha256: Mapped[str] = mapped_column(String(64))
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    item_count: Mapped[int] = mapped_column(Integer, default=0)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Job(Base):
    """Persistent background job. Survives restarts (running jobs are re-queued)."""

    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONText, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONText, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
