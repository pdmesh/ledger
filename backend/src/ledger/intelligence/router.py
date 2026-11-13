"""Task-based model routing with fallbacks, privacy restrictions and execution records."""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from ledger.config import current_version, get_setting
from ledger.intelligence.providers import (
    Provider,
    ProviderConfig,
    ProviderError,
    build_provider,
)
from ledger.models import AIExecution

log = logging.getLogger(__name__)

# Intelligence tasks exposed to the rest of the application.
TASKS = {
    "classify": "Routine transaction classification",
    "merchant": "Merchant normalization",
    "extract": "Document interpretation / complex extraction",
    "identity": "Identity and ownership resolution",
    "reconcile": "Ambiguous reconciliation adjudication",
    "judge": "Second-opinion adjudication for low-confidence decisions",
    "query": "Natural language analytics",
}


class NoProviderAvailable(Exception):
    pass


@dataclass
class TaskOutcome:
    data: Any
    execution_id: int
    provider_id: str
    model: str | None


# A hook so tests (and an offline "evaluation" mode) can inject a provider factory.
ProviderFactory = Callable[[ProviderConfig], Provider]


class IntelligenceRouter:
    def __init__(self, session: Session, provider_factory: ProviderFactory | None = None):
        self.session = session
        self.settings = get_setting(session, "intelligence")
        self.factory = provider_factory or build_provider
        self.providers = {
            p["id"]: ProviderConfig.from_dict(p)
            for p in self.settings.get("providers", [])
            if p.get("enabled", True)
        }

    def chain(self, task: str) -> list[ProviderConfig]:
        routing: dict[str, list[str]] = self.settings.get("routing", {})
        ids = routing.get(task) or routing.get("default") or list(self.providers)
        allow_cloud = bool(self.settings.get("allow_cloud"))
        out = []
        for pid in ids:
            cfg = self.providers.get(pid)
            if cfg is None:
                continue
            if not cfg.is_local and not allow_cloud:
                continue  # privacy routing: cloud/CLI providers need explicit opt-in
            out.append(cfg)
        return out

    def available(self, task: str) -> bool:
        return bool(self.chain(task))

    def run(
        self,
        task: str,
        system: str,
        user: str,
        *,
        validate: Callable[[Any], Any] | None = None,
        item_count: int = 0,
        images: list[Path] | None = None,
    ) -> TaskOutcome:
        """Run ``task`` through the provider chain; first valid result wins."""
        chain = self.chain(task)
        if not chain:
            raise NoProviderAvailable(task)
        prompt_hash = hashlib.sha256((system + "\n" + user).encode()).hexdigest()
        cfg_version = current_version(self.session)
        last_err: str | None = None
        for cfg in chain:
            rec = AIExecution(
                task=task,
                provider_id=cfg.id,
                provider_kind=cfg.kind,
                model=cfg.model,
                status="error",
                prompt_sha256=prompt_hash,
                item_count=item_count,
                config_version=cfg_version,
            )
            try:
                provider = self.factory(cfg)
                result = (
                    provider.complete_json(system, user, images=images)
                    if images
                    else provider.complete_json(system, user)
                )
                rec.model = result.model or cfg.model
                rec.input_tokens = result.input_tokens
                rec.output_tokens = result.output_tokens
                rec.cost_usd = result.cost_usd
                rec.latency_ms = result.latency_ms
                data = validate(result.data) if validate else result.data
                rec.status = "ok"
                self.session.add(rec)
                self.session.flush()
                return TaskOutcome(data, rec.id, cfg.id, rec.model)
            except (ProviderError, ValueError, KeyError, TypeError) as e:
                rec.status = "invalid_output" if not isinstance(e, ProviderError) else "error"
                # Never log prompt contents; errors may include provider messages only.
                rec.error = str(e)[:1000]
                last_err = rec.error
                self.session.add(rec)
                self.session.flush()
                log.warning("intelligence task %s failed on %s: %s", task, cfg.id, rec.error)
        raise NoProviderAvailable(f"{task}: all providers failed ({last_err})")
